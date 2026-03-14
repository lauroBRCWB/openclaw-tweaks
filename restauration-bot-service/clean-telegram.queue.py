#!/usr/bin/env python3
"""Clear all pending updates from the Telegram bot queue."""
import argparse
import os
import sys
from pathlib import Path
from dotenv import load_dotenv
import requests

parser = argparse.ArgumentParser(description='Clear Telegram bot update queue')
parser.add_argument('bot_name', help='Bot name (e.g., RESTAURATION, DEFAULT)')
args = parser.parse_args()

ENV_FILE = Path.home() / '.openclaw' / '.env'
if ENV_FILE.exists():
    load_dotenv(dotenv_path=ENV_FILE, override=False)

bot_key = f'TELEGRAM_BOT_TOKEN_{args.bot_name.upper()}'
TOKEN = os.getenv(bot_key)
if not TOKEN:
    print(
        f'Error: {bot_key} not set in env or .env',
        file=sys.stderr,
    )
    sys.exit(1)

url = f'https://api.telegram.org/bot{TOKEN}/getUpdates'
response = requests.get(url, timeout=10).json()

if not response.get('ok'):
    print(f"Telegram API error: {response.get('description', 'unknown')}", file=sys.stderr)
    sys.exit(1)

if response['result']:
    last_update_id = response['result'][-1]['update_id']
    requests.get(url, params={'offset': last_update_id + 1}, timeout=10)
    print(f'Queue cleared ({len(response["result"])} update(s) flushed).')
else:
    print('Queue already empty.')
