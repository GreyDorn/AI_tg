#!/usr/bin/env bash
# Poll GitHub for new main commits and deploy to this VPS.
# Requires /root/.github_deploy_token with repo read access.
set -euo pipefail

APP_DIR="${APP_DIR:-/root/tg_AI}"
SERVICE_NAME="${SERVICE_NAME:-tg_ai_bot.service}"
PYTHON="${PYTHON:-python3}"
REPO="${GITHUB_REPO:-GreyDorn/AI_tg}"
BRANCH="${DEPLOY_BRANCH:-main}"
TOKEN_FILE="${GITHUB_TOKEN_FILE:-/root/.github_deploy_token}"
STATE_FILE="${APP_DIR}/.deployed_sha"

if [[ ! -f "$TOKEN_FILE" ]]; then
  echo "Missing $TOKEN_FILE"
  exit 1
fi

TOKEN="$(tr -d '[:space:]' < "$TOKEN_FILE")"
REMOTE_SHA="$(
  curl -fsS -H "Authorization: token ${TOKEN}" \
    "https://api.github.com/repos/${REPO}/commits/${BRANCH}" \
  | python3 -c "import sys, json; print(json.load(sys.stdin)['sha'])"
)"

LOCAL_SHA=""
if [[ -f "$STATE_FILE" ]]; then
  LOCAL_SHA="$(tr -d '[:space:]' < "$STATE_FILE")"
fi

if [[ "$REMOTE_SHA" == "$LOCAL_SHA" ]]; then
  echo "Already on ${REMOTE_SHA:0:7}"
  exit 0
fi

echo "Deploying ${REMOTE_SHA:0:7}..."
TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT

curl -fsSL -H "Authorization: token ${TOKEN}" \
  "https://api.github.com/repos/${REPO}/tarball/${BRANCH}" \
  | tar -xz -C "$TMP_DIR" --strip-components=1

RSYNC_OPTS=(-a --delete
  --exclude 'venv/'
  --exclude '.env'
  --exclude 'bot.db'
  --exclude '__pycache__/'
  --exclude '*.pyc'
  --exclude '.deployed_sha'
  --exclude '.github_deploy_token'
)

rsync "${RSYNC_OPTS[@]}" "${TMP_DIR}/" "${APP_DIR}/"

cd "$APP_DIR"
if [[ -f venv/bin/activate ]]; then
  # shellcheck disable=SC1091
  source venv/bin/activate
fi

"$PYTHON" -m pip install -q -r requirements.txt
"$PYTHON" -c "import asyncio; from db.repository import init_db; asyncio.run(init_db())"

if systemctl is-active --quiet "$SERVICE_NAME"; then
  systemctl restart "$SERVICE_NAME"
fi

echo "$REMOTE_SHA" > "$STATE_FILE"
echo "Deployed ${REMOTE_SHA:0:7}"
