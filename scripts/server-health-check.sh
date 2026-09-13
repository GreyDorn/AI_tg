#!/usr/bin/env bash
# Print Telegram bot + gateway status on DE VPS (read-only).
set -euo pipefail

APP_DIR="${APP_DIR:-/root/tg_AI}"
SERVICE_NAME="${SERVICE_NAME:-tg_ai_bot.service}"
GATEWAY_SERVICE_NAME="${GATEWAY_SERVICE_NAME:-llm_gateway.service}"
PYTHON="${PYTHON:-python3}"

echo "=== server-health-check $(date -u +%Y-%m-%dT%H:%M:%SZ) ==="
echo "APP_DIR=$APP_DIR"

if [[ -f "$APP_DIR/.deployed_sha" ]]; then
  echo "deployed_sha=$(tr -d '[:space:]' < "$APP_DIR/.deployed_sha")"
fi

echo "--- systemd ---"
systemctl is-active "$SERVICE_NAME" 2>&1 || true
systemctl is-active "$GATEWAY_SERVICE_NAME" 2>&1 || true
test -f "$APP_DIR/gateway_main.py" && echo "gateway_main.py: present" || echo "gateway_main.py: MISSING"

echo "--- gateway local health ---"
GATEWAY_PORT="$(
  grep -E '^GATEWAY_PORT=' "$APP_DIR/.env" 2>/dev/null | cut -d= -f2 | tr -d '[:space:]' || true
)"
GATEWAY_PORT="${GATEWAY_PORT:-8787}"
curl -sf --max-time 5 "http://127.0.0.1:${GATEWAY_PORT}/health" && echo || echo "gateway health: FAIL on port ${GATEWAY_PORT}"

echo "--- Telegram bot DB stats ---"
cd "$APP_DIR"
if [[ -f venv/bin/activate ]]; then
  # shellcheck disable=SC1091
  source venv/bin/activate
fi
"$PYTHON" - <<'PY' || echo "stats script failed"
import asyncio
from db.repository import SessionFactory, init_db, get_bot_stats

async def main():
    await init_db()
    async with SessionFactory() as session:
        st = await get_bot_stats(session)
        print(f"total_users={st.total_users}")
        print(f"new_today={st.new_today}")
        print(f"active_7d={st.active_users_7d}")
        print(f"messages_total={st.total_user_messages}")
        print(f"messages_today={st.messages_today}")

asyncio.run(main())
PY

echo "--- recent tg bot errors (7d) ---"
journalctl -u "$SERVICE_NAME" --since "7 days ago" --no-pager 2>/dev/null | grep -iE 'error|exception|traceback' | tail -5 || echo "(none or no journal)"

echo "=== end health check ==="
