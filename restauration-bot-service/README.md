# OpenClaw Telegram Restauration Bot

A Telegram bot that accepts deterministic commands and runs them on the Linux host — useful for remote administration of an OpenClaw deployment.

---

- [OpenClaw Telegram Restauration Bot](#openclaw-telegram-restauration-bot)
  - [Commands](#commands)
    - [`/git_pull` ref resolution](#git_pull-ref-resolution)
    - [Inline Command Menu](#inline-command-menu)
  - [Requirements](#requirements)
  - [Deploy script](#deploy-script)
  - [Configuration](#configuration)
    - [Required variables](#required-variables)
  - [Running manually](#running-manually)
  - [Installing as a systemd service](#installing-as-a-systemd-service)
  - [Clearing the Telegram update queue](#clearing-the-telegram-update-queue)
  - [`/reboot` safety](#reboot-safety)
  - [Logs](#logs)

---

## Commands

| Command | Description |
|---|---|
| `/start` or `/help` | List all available commands with inline menu buttons |
| `/menu` | Show the command menu with inline buttons |
| `/ping` | Check if the bot is alive (replies `OK`) |
| `/gateway_alive` | Run `openclaw gateway health` and report the result |
| `/gateway_restart` | Run `openclaw gateway restart` |
| `/git_pull` | Fetch origin and reset repo to `main` |
| `/git_pull <ref>` | Fetch and reset to a branch or tag (e.g. `/git_pull v1.2.3` or `/git_pull origin/feature-x`) |
| `/doctor_deep` | Run `openclaw doctor --deep` with streaming output |
| `/doctor_fix` | Run `openclaw doctor --fix` |
| `/audit_deep` | Run `openclaw security audit --deep` with streaming output |
| `/audit_fix` | Run `openclaw security audit --fix` |
| `/clean_queue` | Clear all pending Telegram bot updates |
| `/reboot confirm` | Reboot the computer (requires the word `confirm` as argument) |
| `/gog_auth` | Start an interactive `gog auth` session |
| `/cancel` | Cancel an active interactive session |

### `/git_pull` ref resolution

- No argument → resets to `origin/main`
- Bare name (e.g. `feature-branch`) → resets to `origin/feature-branch`
- Name with `/` already (e.g. `origin/other`, `tags/v1.0`) → used as-is

### Inline Command Menu

When you send `/start`, `/help`, or `/menu`, the bot displays an **inline keyboard** with buttons for all commands. Tapping a button executes the command without needing to type it.

**Notes:**
- Interactive commands (like `/gog_auth`) and commands with required arguments (like `/reboot confirm`) show usage hints when invoked from the menu.
- Commands with optional arguments (like `/git_pull <ref>`) use sensible defaults when called from the menu (e.g., `git_pull` defaults to `main`).
- The menu is only available to authorized users.

---

## Requirements

- Python 3.10+
- `python-telegram-bot >= 20`
- `python-dotenv`
- `requests`

> **Do not use `pipx`** — it is for CLI tools, not libraries. Use a plain `venv` instead.

---

## Deploy script

`deploy.sh` is the recommended way to install or update the bot. It handles everything end-to-end:

1. **Prompts for missing env vars** and appends them to the `.env` file
2. **Pulls latest code** from `origin/main` (skipped gracefully if the directory is not a git repo)
3. **Patches the service file** with the correct paths and username
4. **Creates the Python venv** and installs dependencies
5. **Adds a sudoers entry** so the bot user can run `/sbin/reboot` without a password
6. **Installs and starts** the systemd service
7. **Shows service status** and optionally tails the journal

```bash
bash deploy.sh [openclaw_dir] [username]
```

| Argument | Default | Description |
|---|---|---|
| `openclaw_dir` | `~/.openclaw` | Path to the openclaw directory |
| `username` | current user (`whoami`) | Linux user that will run the service |

Examples:

```bash
# Defaults: ~/.openclaw, current user
bash deploy.sh

# Custom openclaw dir, explicit username
bash deploy.sh /home/lauro/.openclaw lauro
```

---

## Configuration

The bot reads configuration from (in order of priority):

1. **Environment variables** already set in the shell
2. **`~/.openclaw/.env`** file
3. **`~/.openclaw/openclaw.json`** (for `TELEGRAM_ALLOWED_CHAT_ID` only)

### Required variables

| Variable | Description |
|---|---|
| `TELEGRAM_BOT_TOKEN_RESTAURATION` | Bot token from [@BotFather](https://t.me/BotFather). Falls back to `TELEGRAM_BOT_TOKEN` if not set. |
| `TELEGRAM_ALLOWED_CHAT_ID` | The only chat ID allowed to send commands. Get it from [@userinfobot](https://t.me/userinfobot). |

Example `~/.openclaw/.env`:

```dotenv
TELEGRAM_BOT_TOKEN_RESTAURATION=123456:ABC-your-token-here
TELEGRAM_ALLOWED_CHAT_ID=987654321
```

---

## Running manually

```bash
cd ~/.openclaw/telegram/restauration-bot-service
.venv/bin/python bot.py
```

---

## Installing as a systemd service

The deploy script handles this automatically. To do it manually:

1. Patch the service file with your actual paths and username, then copy it:

```bash
sudo cp openclaw-telegram-bot.service /etc/systemd/system/
```

2. Reload systemd and enable the service:

```bash
sudo systemctl daemon-reload
sudo systemctl enable openclaw-telegram-bot
sudo systemctl start openclaw-telegram-bot
```

3. Check status and logs:

```bash
sudo systemctl status openclaw-telegram-bot
journalctl -u openclaw-telegram-bot -f
```

---

## Clearing the Telegram update queue

If the bot was offline and you want to discard accumulated messages before restarting:

```bash
.venv/bin/python clean-telegram.queue.py
```

The script reads the token from the same env / `.env` sources as the bot.

---

## `/reboot` safety

The `/reboot` command requires `sudo reboot` to be allowed without a password for the service user. The deploy script handles this automatically by writing to `/etc/sudoers.d/openclaw-reboot`.

To do it manually (use `visudo` to edit safely):

```
USERNAME ALL=(ALL) NOPASSWD: /sbin/reboot
```

Replace `USERNAME` with your actual username.

---

## Logs

Logs are written to:

```
~/.openclaw/telegram/restauration-bot-service/log/telegram-git-bot.log
```

And also to stdout / the systemd journal when running as a service.
