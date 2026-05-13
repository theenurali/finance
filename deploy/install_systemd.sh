#!/usr/bin/env bash
set -euo pipefail

APP_DIR="/opt/finance-bot"
UNIT_SRC="$(cd "$(dirname "$0")" && pwd)/finance-bot.service"
UNIT_DST="/etc/systemd/system/finance-bot.service"

if [[ ! -f "$APP_DIR/.env" ]]; then
  echo "ERROR: $APP_DIR/.env not found. Create it first (copy .env.example -> .env and set BOT_TOKEN)."
  exit 2
fi

sudo cp "$UNIT_SRC" "$UNIT_DST"
sudo systemctl daemon-reload
sudo systemctl enable finance-bot
sudo systemctl restart finance-bot
sudo systemctl status finance-bot --no-pager

echo "Logs: journalctl -u finance-bot -f"

