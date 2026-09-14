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
lines = text.splitlines(keepends=True)


def skip_brace_block(start: int) -> int:
    depth = 0
    i = start
    while i < len(lines):
        depth += lines[i].count("{") - lines[i].count("}")
        i += 1
        if i > start and depth <= 0:
            break
    return i


out: list[str] = []
i = 0
removed = 0
while i < len(lines):
    line = lines[i]
    if marker in line:
        i = skip_brace_block(i)
        removed += 1
        continue
    if re.search(r"location\s+[^;{]*/ai-gpt/", line):
        i = skip_brace_block(i)
        removed += 1
        continue
    out.append(line)
    i += 1

text = "".join(out)
if removed:
    print(f"Removed {removed} /ai-gpt/ or managed block(s)")

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
if re.search(r"location\s+[^;{]*/ai-gpt/", text):
    raise SystemExit("Still has /ai-gpt/ location after cleanup — check nginx site")
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

grep -n "ai-gpt" "$NGINX_SITE" || true
