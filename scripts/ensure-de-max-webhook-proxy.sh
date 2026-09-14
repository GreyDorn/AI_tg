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

# Drop managed duplicate blocks entirely.
while marker in text:
    start = text.index(marker)
    rest = text[start:]
    m = re.match(r"(?s).*?\n    \}\n", rest)
    if not m:
        text = text[:start] + rest.lstrip()
        break
    text = text[:start] + rest[m.end():]

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

if "location ^~ /ai-gpt/" not in text:
    anchor = "    location ^~ /uploads/ {"
    if anchor not in text:
        raise SystemExit("No anchor for /ai-gpt/ insert")
    text = text.replace(anchor, managed_block + anchor, 1)
    print("Inserted /ai-gpt/ proxy")
else:
    # Fix proxy_pass in the first /ai-gpt/ block.
    pattern = r"(location \^~ /ai-gpt/\s*\{)(.*?)(\n    \})"

    def fix_block(m: re.Match) -> str:
        body = m.group(2)
        body = re.sub(
            r"proxy_pass\s+[^;]+;",
            f"proxy_pass {upstream}/;",
            body,
            count=1,
        )
        if "proxy_set_header X-Max-Bot-Api-Secret" not in body:
            body = body.replace(
                "proxy_set_header X-Forwarded-Proto $scheme;",
                "proxy_set_header X-Forwarded-Proto $scheme;\n"
                "        proxy_set_header X-Max-Bot-Api-Secret $http_x_max_bot_api_secret;",
            )
        return m.group(1) + body + m.group(3)

    new_text, n = re.subn(pattern, fix_block, text, count=1, flags=re.DOTALL)
    if n:
        text = new_text
        print("Updated /ai-gpt/ proxy_pass →", upstream)
    else:
        print("WARN: /ai-gpt/ present but block not patched")

# Remove extra duplicate /ai-gpt/ blocks (keep first only).
blocks = list(re.finditer(r"location \^~ /ai-gpt/\s*\{.*?\n    \}", text, flags=re.DOTALL))
if len(blocks) > 1:
    for b in reversed(blocks[1:]):
        text = text[: b.start()] + text[b.end() :]
    print("Removed", len(blocks) - 1, "duplicate /ai-gpt/ block(s)")

path.write_text(text)
PY

nginx -t
systemctl reload nginx

echo -n "Public health: "
curl -sf --max-time 10 "https://vpoiskerabot.ru/ai-gpt/health" && echo || echo FAIL

echo -n "DE → RU direct: "
curl -sf --max-time 10 "${RU_MAX_UPSTREAM}/health" && echo || echo FAIL
