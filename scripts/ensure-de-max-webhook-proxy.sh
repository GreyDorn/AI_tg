#!/usr/bin/env bash
# DE VPS: ensure vpoiskerabot.ru /ai-gpt/ proxies to MAX bot on RU VPS.
set -euo pipefail

RU_MAX_UPSTREAM="${RU_MAX_UPSTREAM:-http://195.133.73.52:8090}"
NGINX_SITE="${NGINX_SITE:-/etc/nginx/sites-available/vpoiskerabot.ru}"
MARKER="# MAX bot webhook proxy (managed by ensure-de-max-webhook-proxy.sh)"

if [[ ! -f "$NGINX_SITE" ]]; then
  echo "NGINX site not found: $NGINX_SITE"
  exit 1
fi

export NGINX_SITE MARKER RU_MAX_UPSTREAM

python3 - <<'PY'
import os
import re
from pathlib import Path

path = Path(os.environ["NGINX_SITE"])
marker = os.environ["MARKER"]
upstream = os.environ["RU_MAX_UPSTREAM"].rstrip("/")

text = path.read_text()

# Remove marker-managed blocks.
while marker in text:
    start = text.index(marker)
    rest = text[start:]
    m = re.match(r"(?s).*?\n    \}\n", rest)
    text = text[:start] + (rest[m.end():] if m else "")

# Remove any location block whose header mentions /ai-gpt/
loc_re = re.compile(
    r"\n    location(?: \^~)? /ai-gpt/.*?\n    \}\n",
    re.DOTALL,
)
text, removed = loc_re.subn("\n", text)
if removed:
    print(f"Removed {removed} old /ai-gpt/ location block(s)")

managed_block = f"""    {marker}
    location ^~ /ai-gpt/ {{
        proxy_pass {upstream}/;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header X-Max-Bot-Api-Secret $http_x_max_bot_api_secret;
        proxy_read_timeout 300s;
        proxy_send_timeout 300s;
    }}

"""

anchor = "    location ^~ /uploads/ {"
if anchor not in text:
    raise SystemExit("No anchor for /ai-gpt/ insert")
text = text.replace(anchor, managed_block + anchor, 1)
print("Installed single /ai-gpt/ proxy →", upstream)

path.write_text(text)
PY

nginx -t
systemctl reload nginx

echo -n "Public health: "
curl -sf --max-time 10 "https://vpoiskerabot.ru/ai-gpt/health" && echo || echo FAIL

echo -n "DE → RU direct: "
curl -sf --max-time 10 "${RU_MAX_UPSTREAM}/health" && echo || echo FAIL
