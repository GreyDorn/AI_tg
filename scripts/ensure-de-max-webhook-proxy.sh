#!/usr/bin/env bash
# DE VPS: ensure vpoiskerabot.ru /ai-gpt/ proxies to MAX bot on RU VPS.
set -euo pipefail

RU_MAX_UPSTREAM="${RU_MAX_UPSTREAM:-http://195.133.73.52:8090}"
NGINX_SITE="${NGINX_SITE:-/etc/nginx/sites-available/vpoiskerabot.ru}"
MARKER="# MAX bot webhook proxy (managed by ensure-de-max-webhook-proxy.sh)"
NGINX_ENABLED_DIR="${NGINX_ENABLED_DIR:-/etc/nginx/sites-enabled}"

if [[ ! -f "$NGINX_SITE" ]]; then
  echo "NGINX site not found: $NGINX_SITE"
  exit 1
fi

export NGINX_SITE MARKER RU_MAX_UPSTREAM NGINX_ENABLED_DIR

python3 - <<'PY'
import os
import re
from pathlib import Path

marker = os.environ["MARKER"]
upstream = os.environ["RU_MAX_UPSTREAM"].rstrip("/")
site_path = Path(os.environ["NGINX_SITE"])
enabled_dir = Path(os.environ["NGINX_ENABLED_DIR"])


def skip_brace_block(lines: list[str], start: int) -> int:
    depth = 0
    i = start
    while i < len(lines):
        depth += lines[i].count("{") - lines[i].count("}")
        i += 1
        if i > start and depth <= 0:
            break
    return i


def strip_ai_gpt_blocks(text: str) -> tuple[str, int]:
    lines = text.splitlines(keepends=True)
    out: list[str] = []
    i = 0
    removed = 0
    while i < len(lines):
        line = lines[i]
        if marker in line:
            i = skip_brace_block(lines, i)
            removed += 1
            continue
        if re.search(r"location\s+.*\/ai-gpt", line):
            i = skip_brace_block(lines, i)
            removed += 1
            continue
        out.append(line)
        i += 1
    return "".join(out), removed


def has_ai_gpt_location(text: str) -> bool:
    return bool(re.search(r"location\s+.*\/ai-gpt", text))


# Remove /ai-gpt/ from every enabled site (avoids duplicate location across includes).
config_files: list[Path] = []
for path in sorted(enabled_dir.iterdir()):
    if not path.is_file():
        continue
    try:
        real = path.resolve()
    except OSError:
        real = path
    if real.is_file() and real not in config_files:
        config_files.append(real)
if site_path.resolve() not in config_files and site_path.is_file():
    config_files.append(site_path.resolve())

total_removed = 0
for cfg in config_files:
    try:
        text = cfg.read_text()
    except OSError:
        continue
    if "/ai-gpt" not in text and marker not in text:
        continue
    cleaned, removed = strip_ai_gpt_blocks(text)
    if removed:
        print(f"Removed {removed} /ai-gpt block(s) from {cfg}")
        total_removed += removed
        cfg.write_text(cleaned)

if total_removed:
    print(f"Total removed blocks: {total_removed}")

text = site_path.read_text()
if has_ai_gpt_location(text):
    raise SystemExit(f"Still has /ai-gpt/ in {site_path} after cleanup")

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
site_path.write_text(text)

# Fail if any enabled config still defines /ai-gpt/ besides our managed block.
for cfg in config_files:
    if cfg == site_path.resolve():
        continue
    t = cfg.read_text()
    if has_ai_gpt_location(t):
        raise SystemExit(f"Duplicate /ai-gpt/ location remains in {cfg}")
PY

# Stray MAX bot on DE would answer webhooks locally instead of RU.
if systemctl is-active max_ai_bot.service >/dev/null 2>&1; then
  echo "Stopping local max_ai_bot.service on DE (MAX runs on RU only)"
  systemctl stop max_ai_bot.service || true
  systemctl disable max_ai_bot.service || true
fi

nginx -t
systemctl reload nginx

echo "Effective nginx /ai-gpt/ (must proxy to RU):"
nginx -T 2>/dev/null | grep -E "location.*ai-gpt|proxy_pass.*8090" || true

echo "ai-gpt lines in nginx enabled:"
grep -rn "/ai-gpt" "$NGINX_ENABLED_DIR/" || true

echo -n "RU upstream health: "
curl -sf --max-time 10 "${RU_MAX_UPSTREAM}/health" && echo || echo FAIL

echo -n "Public health: "
curl -sf --max-time 10 "https://vpoiskerabot.ru/ai-gpt/health" && echo || echo FAIL

grep -n "ai-gpt" "$NGINX_SITE" || true
