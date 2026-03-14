#!/usr/bin/env python3
import argparse
import asyncio
import html
import json
import logging
import os
import sys
import subprocess
from pathlib import Path
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    ConversationHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

GOG_PATH='/home/linuxbrew/.linuxbrew/bin/gog'  # Adjust if gog is installed elsewhere
# ─── CLI args — parsed first so ENV_FILE can be overridden before anything runs ──

_parser = argparse.ArgumentParser(description='OpenClaw Telegram restauration bot')
_parser.add_argument(
    '--env-file',
    metavar='PATH',
    type=Path,
    default=None,
    help='Path to .env file (default: ~/.openclaw/.env)',
)
_parser.add_argument(
    '--openclaw-dir',
    metavar='PATH',
    type=Path,
    default=None,
    help='Path to openclaw directory (default: ~/.openclaw)',
)
_args = _parser.parse_args()

# ─── Paths ────────────────────────────────────────────────────────────────────

HOME = Path.home()
OPENCLAW_DIR = _args.openclaw_dir if _args.openclaw_dir is not None else HOME / '.openclaw'
TELEGRAM_DIR = OPENCLAW_DIR / 'telegram/restauration-bot-service'
LOG_DIR = TELEGRAM_DIR / 'log'
LOG_DIR.mkdir(parents=True, exist_ok=True)

ENV_FILE: Path = _args.env_file if _args.env_file is not None else OPENCLAW_DIR / '.env'
OPENCLAW_JSON = OPENCLAW_DIR / 'openclaw.json'
CLEAN_QUEUE_SCRIPT = TELEGRAM_DIR / 'clean-telegram.queue.py'
BOT_LOG_FILE = LOG_DIR / 'telegram-git-bot.log'

REPO_DIR = str(OPENCLAW_DIR)
DEFAULT_BRANCH = 'main'
MAX_MSG_LEN = 3800  # Telegram limit is 4096; leave headroom for HTML tags

# ─── Logging ──────────────────────────────────────────────────────────────────
# Load .env early so LOGLEVEL set there is respected by the logging setup.
# override=False means shell env always wins over .env.
if ENV_FILE.exists():
    load_dotenv(dotenv_path=ENV_FILE, override=False)

_log_level = getattr(logging, os.environ.get('LOGLEVEL', 'INFO').upper(), logging.INFO)
logging.basicConfig(
    level=_log_level,
    format='%(asctime)s %(levelname)s %(name)s %(message)s',
    handlers=[
        logging.FileHandler(BOT_LOG_FILE),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger(__name__)

# ─── Config ───────────────────────────────────────────────────────────────────


def _load_dotenv_once() -> bool:
    """Load ~/.openclaw/.env into os.environ (shell vars are never overridden).
    Returns True if the file was found and loaded."""
    if ENV_FILE.exists():
        load_dotenv(dotenv_path=ENV_FILE, override=False)
        logger.info('Loaded .env from %s', ENV_FILE)
        return True
    logger.warning('.env not found at %s', ENV_FILE)
    return False


def read_allowed_chat_id_from_openclaw_json() -> int | None:
    if not OPENCLAW_JSON.exists():
        logger.warning('openclaw.json not found at %s', OPENCLAW_JSON)
        return None
    try:
        with OPENCLAW_JSON.open('r', encoding='utf-8') as f:
            data = json.load(f)
        value = data['approvals']['exec']['targets'][0]['to']
        result = int(value) if value is not None else None
        if result is not None:
            logger.info('Read TELEGRAM_ALLOWED_CHAT_ID from openclaw.json: %d', result)
        return result
    except (KeyError, IndexError, TypeError, ValueError, json.JSONDecodeError) as exc:
        logger.error('Failed to read TELEGRAM_ALLOWED_CHAT_ID from openclaw.json: %s', exc)
        return None


def _resolve_token() -> str | None:
    """Resolve bot token with explicit source logging.
    Priority: shell env → .env file → give up (openclaw.json has no token).
    """
    # Step 1: shell environment (already in os.environ before any dotenv load)
    for key in ('TELEGRAM_BOT_TOKEN_RESTAURATION', 'TELEGRAM_BOT_TOKEN'):
        val = os.environ.get(key)
        if val:
            logger.info('Bot token resolved from shell env / .env (%s)', key)
            return val

    logger.error(
        'Bot token not found. Checked TELEGRAM_BOT_TOKEN_RESTAURATION and '
        'TELEGRAM_BOT_TOKEN in shell env and %s', ENV_FILE
    )
    return None


def _resolve_chat_id() -> int | None:
    """Resolve allowed chat ID with explicit source logging.
    Priority: shell env → .env file → openclaw.json.
    """
    # Step 1: shell env / .env (already merged by the early load_dotenv call)
    raw = os.environ.get('TELEGRAM_ALLOWED_CHAT_ID')
    if raw:
        try:
            val = int(raw)
            logger.info('TELEGRAM_ALLOWED_CHAT_ID resolved from shell env / .env: %d', val)
            return val
        except ValueError:
            logger.error('TELEGRAM_ALLOWED_CHAT_ID is not a valid integer: %r', raw)

    # Step 2: openclaw.json
    logger.info(
        'TELEGRAM_ALLOWED_CHAT_ID not in shell env or .env — trying openclaw.json'
    )
    return read_allowed_chat_id_from_openclaw_json()


def resolve_config() -> tuple[str, int]:
    logger.info(
        'Resolving config — .env: %s (exists=%s), openclaw.json: %s (exists=%s)',
        ENV_FILE, ENV_FILE.exists(), OPENCLAW_JSON, OPENCLAW_JSON.exists(),
    )

    # .env was already loaded at module level for LOGLEVEL; call again is a no-op
    # for vars already set, but picks up anything missed if file appeared late.
    _load_dotenv_once()

    bot_token = _resolve_token()
    allowed_chat_id = _resolve_chat_id()

    if not bot_token:
        raise RuntimeError(
            'Neither TELEGRAM_BOT_TOKEN_RESTAURATION nor TELEGRAM_BOT_TOKEN found '
            f'in shell environment or {ENV_FILE}'
        )
    if allowed_chat_id is None:
        raise RuntimeError(
            'TELEGRAM_ALLOWED_CHAT_ID not found in shell environment, '
            f'{ENV_FILE}, or {OPENCLAW_JSON}'
        )

    logger.info(
        'Config OK — allowed_chat_id=%d, token ends ...%s',
        allowed_chat_id, bot_token[-6:],
    )
    return bot_token, allowed_chat_id


BOT_TOKEN, ALLOWED_CHAT_ID = resolve_config()

# ─── Helpers ──────────────────────────────────────────────────────────────────


def is_authorized(update: Update) -> bool:
    chat = update.effective_chat
    return chat is not None and chat.id == ALLOWED_CHAT_ID


async def send_chunks(update: Update, text: str, header: str = '') -> None:
    """Send text split into MAX_MSG_LEN HTML <pre> blocks."""
    if header:
        await update.message.reply_text(header)
    if not text:
        return
    lines = text.splitlines(keepends=True)
    chunk = ''
    for line in lines:
        if len(chunk) + len(line) > MAX_MSG_LEN:
            await update.message.reply_text(
                f'<pre>{html.escape(chunk)}</pre>', parse_mode='HTML'
            )
            chunk = ''
        chunk += line
    if chunk:
        await update.message.reply_text(
            f'<pre>{html.escape(chunk)}</pre>', parse_mode='HTML'
        )


async def run_simple(cmd: list[str], timeout: int = 120) -> tuple[int, str]:
    """Run a command in a thread and return (returncode, combined output)."""
    loop = asyncio.get_running_loop()

    def _run() -> tuple[int, str]:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
            env={**os.environ},
        )
        return result.returncode, (result.stdout + result.stderr).strip()

    return await loop.run_in_executor(None, _run)


async def run_streaming(cmd: list[str], update: Update, timeout: int = 600) -> None:
    """Run a long-running command and stream its output to Telegram every few seconds."""
    await update.message.reply_text(
        f'Running: <code>{html.escape(" ".join(cmd))}</code>', parse_mode='HTML'
    )
    msg = await update.message.reply_text('<pre>...</pre>', parse_mode='HTML')

    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
        env={**os.environ},
    )

    buffer = ''
    last_edit = asyncio.get_running_loop().time()
    edit_interval = 3.0

    async def _read_loop() -> None:
        nonlocal buffer, last_edit
        assert proc.stdout is not None
        async for raw in proc.stdout:
            buffer += raw.decode('utf-8', errors='replace')
            now = asyncio.get_running_loop().time()
            if now - last_edit >= edit_interval:
                tail = buffer[-MAX_MSG_LEN:]
                try:
                    await msg.edit_text(
                        f'<pre>{html.escape(tail)}</pre>', parse_mode='HTML'
                    )
                    last_edit = now
                except Exception:
                    pass

    try:
        await asyncio.wait_for(_read_loop(), timeout=timeout)
    except asyncio.TimeoutError:
        proc.terminate()
        await update.message.reply_text(f'Timed out after {timeout}s.')

    await proc.wait()

    # Final edit with tail
    if buffer:
        tail = buffer[-MAX_MSG_LEN:]
        try:
            await msg.edit_text(f'<pre>{html.escape(tail)}</pre>', parse_mode='HTML')
        except Exception:
            pass
        if len(buffer) > MAX_MSG_LEN:
            await update.message.reply_text(
                f'(Output truncated — {len(buffer)} chars total, showing last {MAX_MSG_LEN}.)'
            )

    status = '✅ Exit 0' if proc.returncode == 0 else f'❌ Exit {proc.returncode}'
    await update.message.reply_text(status)


# ─── Command Handlers ─────────────────────────────────────────────────────────

def get_available_bots() -> dict[str, str]:
    """Extract all TELEGRAM_BOT_TOKEN_* entries from .env file.
    Returns a dict of {name: token} where name is lowercase without prefix.
    """
    bots = {}
    if ENV_FILE.exists():
        with open(ENV_FILE, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line.startswith('TELEGRAM_BOT_TOKEN_') and '=' in line:
                    key, value = line.split('=', 1)
                    name = key.replace('TELEGRAM_BOT_TOKEN_', '').lower()
                    if value:
                        bots[name] = value
    return bots


HELP_TEXT = (
    'Restauration bot commands:\n\n'
    '/ping — check bot is alive\n'
    '/gateway_alive — check openclaw gateway health\n'
    '/gateway_restart — restart openclaw gateway\n'
    '/git_pull [ref] — reset repo to ref (default: main)\n'
    '/doctor_deep — openclaw doctor --deep (streamed)\n'
    '/doctor_fix — openclaw doctor --fix\n'
    '/audit_deep — openclaw security audit --deep (streamed)\n'
    '/audit_fix — openclaw security audit --fix\n'
    '/clean_queue — clear Telegram update queue (interactive)\n'
    '/reboot confirm — reboot this computer\n'
    '/restart_service — restart openclaw-telegram-bot service\n'
    '/gog_auth — interactive gog authentication\n'
    '/cancel — cancel interactive session'
)


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_authorized(update):
        await update.message.reply_text('Unauthorized.')
        return
    await update.message.reply_text(HELP_TEXT)


async def cmd_ping(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_authorized(update):
        await update.message.reply_text('Unauthorized.')
        return
    await update.message.reply_text('OK')


async def cmd_gateway_alive(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_authorized(update):
        await update.message.reply_text('Unauthorized.')
        return
    await update.message.reply_text('Checking gateway health...')
    code, output = await run_simple(['openclaw', 'gateway', 'health'], timeout=30)
    header = '✅ Gateway is healthy.' if code == 0 else f'❌ Gateway health check failed (exit {code}).'
    await send_chunks(update, output, header=header)


async def cmd_gateway_restart(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_authorized(update):
        await update.message.reply_text('Unauthorized.')
        return
    await update.message.reply_text('Restarting openclaw gateway...')
    code, output = await run_simple(['openclaw', 'gateway', 'restart'], timeout=60)
    header = '✅ Gateway restarted.' if code == 0 else f'❌ Gateway restart failed (exit {code}).'
    await send_chunks(update, output, header=header)


async def cmd_git_pull(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_authorized(update):
        await update.message.reply_text('Unauthorized.')
        return

    ref = context.args[0] if context.args else None

    # If ref has no '/', treat it as a branch name and prefix with origin/.
    # If it already has '/' (e.g. origin/branch, tags/v1.0), use as-is.
    if ref is None:
        target = f'origin/{DEFAULT_BRANCH}'
    elif '/' in ref:
        target = ref
    else:
        target = f'origin/{ref}'

    await update.message.reply_text(
        f'Fetching and resetting to <code>{html.escape(target)}</code>...', parse_mode='HTML'
    )

    fetch_code, fetch_out = await run_simple(
        ['git', '-C', REPO_DIR, 'fetch', '--all', '--tags'], timeout=60
    )
    if fetch_code != 0:
        await send_chunks(update, fetch_out, header=f'❌ git fetch failed (exit {fetch_code}).')
        return

    reset_code, reset_out = await run_simple(
        ['git', '-C', REPO_DIR, 'reset', '--hard', target], timeout=30
    )
    clean_code, clean_out = await run_simple(
        ['git', '-C', REPO_DIR, 'clean', '-fd'], timeout=30
    )

    combined = '\n'.join(filter(None, [fetch_out, reset_out, clean_out]))
    if reset_code == 0:
        header = f'✅ Reset to {target}.'
    else:
        header = f'❌ git reset failed (exit {reset_code}).'
    await send_chunks(update, combined, header=header)


async def cmd_doctor_deep(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_authorized(update):
        await update.message.reply_text('Unauthorized.')
        return
    await run_streaming(['openclaw', 'doctor', '--deep'], update, timeout=600)


async def cmd_doctor_fix(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_authorized(update):
        await update.message.reply_text('Unauthorized.')
        return
    await update.message.reply_text('Running openclaw doctor --fix...')
    code, output = await run_simple(['openclaw', 'doctor', '--fix'], timeout=300)
    header = '✅ Done.' if code == 0 else f'❌ Failed (exit {code}).'
    await send_chunks(update, output, header=header)


async def cmd_audit_deep(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_authorized(update):
        await update.message.reply_text('Unauthorized.')
        return
    await run_streaming(['openclaw', 'security', 'audit', '--deep'], update, timeout=600)


async def cmd_audit_fix(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_authorized(update):
        await update.message.reply_text('Unauthorized.')
        return
    await update.message.reply_text('Running openclaw security audit --fix...')
    code, output = await run_simple(['openclaw', 'security', 'audit', '--fix'], timeout=300)
    header = '✅ Done.' if code == 0 else f'❌ Failed (exit {code}).'
    await send_chunks(update, output, header=header)


# ─── clean_queue — interactive ConversationHandler ─────────────────────────

CLEAN_QUEUE_BOT_SELECTION = 0


async def cmd_clean_queue(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if not is_authorized(update):
        await update.message.reply_text('Unauthorized.')
        return ConversationHandler.END

    bots = get_available_bots()
    if not bots:
        await update.message.reply_text('❌ No bots found in .env file.')
        return ConversationHandler.END

    context.user_data['available_bots'] = bots

    # Build list of available bots
    bot_list = '\n'.join(f'{i + 1}. {name.upper()}' for i, name in enumerate(bots.keys()))
    await update.message.reply_text(
        f'Which bot queue should I clean?\n\n{bot_list}\n\nSend the number or bot name:'
    )
    return CLEAN_QUEUE_BOT_SELECTION


async def clean_queue_bot_selection(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    bots = context.user_data.get('available_bots', {})
    user_input = update.message.text.strip().lower()

    # Try to match by number
    bot_names = list(bots.keys())
    try:
        idx = int(user_input) - 1
        if 0 <= idx < len(bot_names):
            selected_bot = bot_names[idx]
        else:
            await update.message.reply_text(f'Invalid selection. Please send a number between 1 and {len(bot_names)}.')
            return CLEAN_QUEUE_BOT_SELECTION
    except ValueError:
        # Try to match by name
        if user_input in bots:
            selected_bot = user_input
        else:
            await update.message.reply_text(f'Bot not found. Available: {", ".join(bot_names)}')
            return CLEAN_QUEUE_BOT_SELECTION

    # Clear the queue for selected bot
    await update.message.reply_text(f'Clearing {selected_bot.upper()} queue...')
    code, output = await run_simple(
        [sys.executable, str(CLEAN_QUEUE_SCRIPT), selected_bot], timeout=30
    )
    header = '✅ Queue cleared.' if code == 0 else f'❌ Failed (exit {code}).'
    await send_chunks(update, output, header=header)
    return ConversationHandler.END


async def cmd_reboot(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_authorized(update):
        await update.message.reply_text('Unauthorized.')
        return
    if not context.args or context.args[0].lower() != 'confirm':
        await update.message.reply_text(
            '⚠️ This will reboot the computer.\n'
            'To confirm, send: /reboot confirm'
        )
        return
    await update.message.reply_text('Rebooting now...')
    code, output = await run_simple(['sudo', 'reboot'], timeout=15)
    # If we reach here, reboot didn't trigger (e.g. sudo denied)
    header = '✅ Reboot initiated.' if code == 0 else f'❌ Reboot failed (exit {code}).'
    await send_chunks(update, output, header=header)


async def cmd_restart_service(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_authorized(update):
        await update.message.reply_text('Unauthorized.')
        return
    await update.message.reply_text('Restarting openclaw-telegram-bot service...')
    code, output = await run_simple(['systemctl', 'restart', 'openclaw-telegram-bot'], timeout=60)
    header = '✅ Service restarted.' if code == 0 else f'❌ Service restart failed (exit {code}).'
    await send_chunks(update, output, header=header)


# ─── gog auth — interactive ConversationHandler ───────────────────────────────

GOG_EMAIL_INPUT = 0
GOG_AUTH_URL_INPUT = 1


async def cmd_gog_auth(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if not is_authorized(update):
        await update.message.reply_text('Unauthorized.')
        return ConversationHandler.END

    await update.message.reply_text('GOG authentication (2 steps)\n\nStep 1: Enter your email address:')
    return GOG_EMAIL_INPUT


async def gog_handle_email(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    email = update.message.text.strip()
    if not email or '@' not in email:
        await update.message.reply_text('Invalid email. Please send a valid email address:')
        return GOG_EMAIL_INPUT

    context.user_data['gog_email'] = email

    # Set up credentials first
    # await update.message.reply_text(f'Setting up credentials for {email}...')
    # credentials_path = os.path.expanduser('~/.credentials/gog-calendar-credentials.json')
    # code, output = await run_simple([GOG_PATH, 'auth', 'credentials', credentials_path], timeout=30)
    # if code != 0:
    #     # and output does not contain "permission denied" we continue, because the credentials are probably configured
    #     if 'permission denied' not in output.lower() and 'permission denied' not in update.lower():            
    #         await send_chunks(update, output, header=f'❌ Credentials setup failed (exit {code}).')
    #         return ConversationHandler.END

    # Step 1: Run gog auth add with --step 1
    await update.message.reply_text(f'Running step 1 for {email}...')
    code, output = await run_simple(
        [GOG_PATH, 'auth', 'add', email, '--services', 'user', '--remote', '--step', '1'],
        timeout=30
    )

    if code != 0:
        await send_chunks(update, output, header=f'❌ Step 1 failed (exit {code}).')
        return ConversationHandler.END

    await send_chunks(update, output, header='✅ Step 1: Auth URL generated.')
    await update.message.reply_text(
        'Step 2: Open the URL above in your browser, authenticate, and paste the full redirect URL from the address bar (starting with http://127.0.0.1):'
    )
    return GOG_AUTH_URL_INPUT


async def gog_handle_auth_url(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    auth_url = update.message.text.strip()
    email = context.user_data.get('gog_email', '')

    if not auth_url or not auth_url.startswith('http'):
        await update.message.reply_text('Invalid URL. Please send the full redirect URL starting with http://127.0.0.1:')
        return GOG_AUTH_URL_INPUT

    # Step 2: Run gog auth add with --step 2 and --auth-url
    await update.message.reply_text(f'Running step 2 for {email}...')
    code, output = await run_simple(
        [GOG_PATH, 'auth', 'add', email, '--services', 'user', '--remote', '--step', '2', '--auth-url', auth_url],
        timeout=30
    )

    header = '✅ Authentication successful.' if code == 0 else f'❌ Step 2 failed (exit {code}).'
    await send_chunks(update, output, header=header)
    return ConversationHandler.END


async def gog_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    proc = context.user_data.pop('gog_proc', None)
    if proc:
        proc.terminate()
    await update.message.reply_text('gog auth cancelled.')
    return ConversationHandler.END


# ─── Main ─────────────────────────────────────────────────────────────────────


def main() -> None:
    logger.info('Starting Telegram restauration bot')
    logger.info('Env file: %s', ENV_FILE)
    logger.info('Allowed chat id: %s', ALLOWED_CHAT_ID)

    app = Application.builder().token(BOT_TOKEN).build()

    # Simple commands
    app.add_handler(CommandHandler('start', cmd_start))
    app.add_handler(CommandHandler('help', cmd_start))
    app.add_handler(CommandHandler('ping', cmd_ping))
    app.add_handler(CommandHandler('gateway_alive', cmd_gateway_alive))
    app.add_handler(CommandHandler('gateway_restart', cmd_gateway_restart))
    app.add_handler(CommandHandler('git_pull', cmd_git_pull))
    app.add_handler(CommandHandler('doctor_deep', cmd_doctor_deep))
    app.add_handler(CommandHandler('doctor_fix', cmd_doctor_fix))
    app.add_handler(CommandHandler('audit_deep', cmd_audit_deep))
    app.add_handler(CommandHandler('audit_fix', cmd_audit_fix))
    app.add_handler(CommandHandler('reboot', cmd_reboot))
    app.add_handler(CommandHandler('restart_service', cmd_restart_service))

    # Interactive clean_queue
    clean_queue_conv = ConversationHandler(
        entry_points=[CommandHandler('clean_queue', cmd_clean_queue)],
        states={
            CLEAN_QUEUE_BOT_SELECTION: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, clean_queue_bot_selection),
            ],
        },
        fallbacks=[CommandHandler('cancel', gog_cancel)],
    )
    app.add_handler(clean_queue_conv)

    # Interactive gog auth
    gog_conv = ConversationHandler(
        entry_points=[CommandHandler('gog_auth', cmd_gog_auth)],
        states={
            GOG_EMAIL_INPUT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, gog_handle_email),
            ],
            GOG_AUTH_URL_INPUT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, gog_handle_auth_url),
            ],
        },
        fallbacks=[CommandHandler('cancel', gog_cancel)],
    )
    app.add_handler(gog_conv)

    app.run_polling()


if __name__ == '__main__':
    main()
