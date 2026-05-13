#!/usr/bin/env bash
set -euo pipefail

APP_DIR="/opt/finance-bot"

sudo apt-get update
sudo apt-get install -y python3 python3-venv python3-pip git

sudo mkdir -p "$APP_DIR"
sudo chown -R "$USER:$USER" "$APP_DIR"

echo "OK: base packages installed, app dir ready at $APP_DIR"

