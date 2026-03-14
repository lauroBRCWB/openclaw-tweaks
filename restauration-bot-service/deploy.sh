#!/usr/bin/env bash
set -euo pipefail

OPENCLAW_DIR="${1:-${HOME}/.openclaw}"
USERNAME="${2:-$(whoami)}"
ENV_FILE="${OPENCLAW_DIR}/.env"
BOT_SERVICE_DIR="${OPENCLAW_DIR}/telegram/restauration-bot-service"
SERVICE_FILE="${BOT_SERVICE_DIR}/openclaw-telegram-bot.service"

# ─── Collect required environment variables ───────────────────────────────────
# Variables needed by bot.py and clean-telegram.queue.py.
# LOGLEVEL is optional (defaults to INFO) — skipped if already set.
REQUIRED_VARS=(
  "TELEGRAM_BOT_TOKEN_RESTAURATION"
  "TELEGRAM_ALLOWED_CHAT_ID"
)
OPTIONAL_VARS=(
  "LOGLEVEL"
)

collect_env_vars() {
  mkdir -p "$(dirname "$ENV_FILE")"
  touch "$ENV_FILE"

  local any_prompted=0

  for var in "${REQUIRED_VARS[@]}"; do
    # Check shell env first, then .env file
    if [[ -n "${!var:-}" ]]; then
      continue
    fi
    if grep -qE "^${var}=" "$ENV_FILE" 2>/dev/null; then
      continue
    fi
    read -rp "${var}: " value </dev/tty
    if [[ -z "$value" ]]; then
      echo "Error: ${var} is required." >&2
      exit 1
    fi
    echo "${var}=${value}" >> "$ENV_FILE"
    any_prompted=1
  done

  for var in "${OPTIONAL_VARS[@]}"; do
    if [[ -n "${!var:-}" ]]; then
      continue
    fi
    if grep -qE "^${var}=" "$ENV_FILE" 2>/dev/null; then
      continue
    fi
    read -rp "${var} (optional, press Enter to skip): " value </dev/tty
    if [[ -n "$value" ]]; then
      echo "${var}=${value}" >> "$ENV_FILE"
      any_prompted=1
    fi
  done

  if [[ $any_prompted -eq 1 ]]; then
    echo "Environment variables saved to ${ENV_FILE}"
  fi
}

collect_env_vars

REPO_DIR="${OPENCLAW_DIR}"
BRANCH="main"
LOG_DIR="${OPENCLAW_DIR}/telegram/restauration-bot-service/log"
LOG_FILE="${LOG_DIR}/telegram-git-bot-deploy.log"

mkdir -p "$LOG_DIR"

{
  echo "[$(date '+%Y-%m-%d %H:%M:%S')] Starting deploy"

  if git -C "$REPO_DIR" rev-parse --git-dir > /dev/null 2>&1; then
    cd "$REPO_DIR"
    git fetch origin
    git reset --hard "origin/$BRANCH"
    git clean -fd
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] Git deploy finished successfully"
  else
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] WARNING: ${REPO_DIR} is not a git repo — skipping git steps"
  fi

  # ─── Patch service file ─────────────────────────────────────────────────────
  sed -i \
    -e "s|^User=.*|User=${USERNAME}|" \
    -e "s|^WorkingDirectory=.*|WorkingDirectory=${BOT_SERVICE_DIR}|" \
    -e "s|^ExecStart=.*|ExecStart=${BOT_SERVICE_DIR}/.venv/bin/python ${BOT_SERVICE_DIR}/bot.py|" \
    "$SERVICE_FILE"
} >> "$LOG_FILE" 2>&1

# ─── Python venv + dependencies ───────────────────────────────────────────────
echo "Setting up Python venv..."
cd "$BOT_SERVICE_DIR"
python3 -m venv .venv
.venv/bin/pip install "python-telegram-bot>=20" python-dotenv requests

# ─── Sudoers entry for reboot ──────────────────────────────────────────────────
SUDOERS_LINE="${USERNAME} ALL=(ALL) NOPASSWD: /sbin/reboot"
SUDOERS_FILE="/etc/sudoers.d/openclaw-reboot"
if sudo grep -qF "$SUDOERS_LINE" "$SUDOERS_FILE" 2>/dev/null; then
  echo "Sudoers entry already present."
else
  echo "Adding sudoers entry for reboot..."
  echo "$SUDOERS_LINE" | sudo tee "$SUDOERS_FILE" > /dev/null
  sudo chmod 440 "$SUDOERS_FILE"
fi

# ─── Install + start systemd service ──────────────────────────────────────────
echo "Installing systemd service..."
sudo cp "$SERVICE_FILE" /etc/systemd/system/openclaw-telegram-bot.service
sudo systemctl daemon-reload
sudo systemctl enable openclaw-telegram-bot
sudo systemctl start openclaw-telegram-bot

echo ""
sudo systemctl status openclaw-telegram-bot

# ─── Optional log tail ────────────────────────────────────────────────────────
echo ""
read -rp "Follow logs? [y/N] " follow </dev/tty
if [[ "${follow,,}" == "y" ]]; then
  journalctl -u openclaw-telegram-bot -f
fi