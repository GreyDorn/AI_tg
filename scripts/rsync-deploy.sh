#!/usr/bin/env bash
# Safe rsync deploy to VPS. Syncs project ROOT contents (not parent folders).
#
# Usage:
#   SSHPASS=your_password ./scripts/rsync-deploy.sh
#   DEPLOY_REMOTE=root@1.2.3.4 DEPLOY_REMOTE_DIR=/root/tg_AI ./scripts/rsync-deploy.sh
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
REMOTE="${DEPLOY_REMOTE:-root@151.243.180.58}"
REMOTE_DIR="${DEPLOY_REMOTE_DIR:-/root/tg_AI}"
SERVICE_NAME="${DEPLOY_SERVICE_NAME:-tg_ai_bot.service}"
PYTHON="${DEPLOY_PYTHON:-python3}"

RSYNC_OPTS=(-avz --delete
  --exclude '.git/'
  --exclude 'venv/'
  --exclude '.env'
  --exclude 'bot.db'
  --exclude '__pycache__/'
  --exclude '*.pyc'
  --exclude '.cursor/'
  --exclude 'workspace/'
)

if [[ -n "${SSHPASS:-}" ]] && command -v sshpass >/dev/null 2>&1; then
  # Cursor sets SSH_ASKPASS vars that break sshpass; unset them for deploy.
  RSYNC_CMD=(env -u SSH_ASKPASS -u SSH_ASKPASS_REQUIRE -u DISPLAY sshpass -e rsync)
  RSYNC_SSH=(env -u SSH_ASKPASS -u SSH_ASKPASS_REQUIRE -u DISPLAY sshpass -e ssh -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -o PreferredAuthentications=password -o PubkeyAuthentication=no)
  SSH_CMD=(env -u SSH_ASKPASS -u SSH_ASKPASS_REQUIRE -u DISPLAY sshpass -e ssh -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -o PreferredAuthentications=password -o PubkeyAuthentication=no)
else
  RSYNC_CMD=(rsync)
  RSYNC_SSH=(ssh -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null)
  SSH_CMD=(ssh -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null)
fi

echo "Deploying ${ROOT_DIR}/ -> ${REMOTE}:${REMOTE_DIR}/"
"${RSYNC_CMD[@]}" -e "${RSYNC_SSH[*]}" "${RSYNC_OPTS[@]}" "${ROOT_DIR}/" "${REMOTE}:${REMOTE_DIR}/"

echo "Running DB migration and restarting ${SERVICE_NAME}..."
"${SSH_CMD[@]}" "${REMOTE}" bash -s <<EOF
set -euo pipefail
cd "${REMOTE_DIR}"
if [[ -f venv/bin/activate ]]; then
  source venv/bin/activate
fi
${PYTHON} -c "import asyncio; from db.repository import init_db; asyncio.run(init_db())"
systemctl restart "${SERVICE_NAME}"
systemctl is-active "${SERVICE_NAME}"
EOF

echo "Deploy complete."
