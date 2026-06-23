#!/usr/bin/env bash
set -euo pipefail

APP_DIR="${APP_DIR:-/root/tg_AI}"
SERVICE_NAME="${SERVICE_NAME:-tg_ai_bot.service}"
PYTHON="${PYTHON:-python3}"

cd "$APP_DIR"

git fetch origin main
git checkout main
git pull --ff-only origin main

if [[ -f venv/bin/activate ]]; then
  source venv/bin/activate
fi

"$PYTHON" -m pip install -r requirements.txt
"$PYTHON" -c "import asyncio; from db.repository import init_db; asyncio.run(init_db())"

if systemctl is-active --quiet "$SERVICE_NAME"; then
  sudo systemctl restart "$SERVICE_NAME"
  sudo systemctl status "$SERVICE_NAME" --no-pager -l
else
  echo "Service $SERVICE_NAME is not configured. Start manually:"
  echo "  cd $APP_DIR && $PYTHON main.py"
fi
