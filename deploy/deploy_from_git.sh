#!/usr/bin/env bash
set -euo pipefail

APP_DIR="/opt/finance-bot"
REPO_URL="${1:-https://github.com/theenurali/finance.git}"

echo "Using repo: $REPO_URL"

mkdir -p "$APP_DIR"
if [[ ! -d "$APP_DIR/.git" ]]; then
  git clone "$REPO_URL" "$APP_DIR"
else
  git -C "$APP_DIR" pull --ff-only
fi

python3 -m venv "$APP_DIR/.venv"
"$APP_DIR/.venv/bin/python" -m pip install --upgrade pip
"$APP_DIR/.venv/bin/python" -m pip install -r "$APP_DIR/requirements.txt"

echo "OK: code updated and dependencies installed"
echo "Next: create $APP_DIR/.env (copy from .env.example) and install systemd unit."
