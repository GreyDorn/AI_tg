#!/usr/bin/env bash
set -euo pipefail

APP_DIR="${APP_DIR:-/opt/AI_tg}"
SERVICE_NAME="${SERVICE_NAME:-ai-tg-bot}"
PYTHON="${PYTHON:-python3}"

cd "$APP_DIR"

git fetch origin main
git checkout main
git pull --ff-only origin main

"$PYTHON" -m pip install -r requirements.txt

if systemctl is-active --quiet "$SERVICE_NAME"; then
  sudo systemctl restart "$SERVICE_NAME"
  sudo systemctl status "$SERVICE_NAME" --no-pager -l
else
  echo "Service $SERVICE_NAME is not configured. Start manually:"
  echo "  cd $APP_DIR && $PYTHON main.py"
fi
