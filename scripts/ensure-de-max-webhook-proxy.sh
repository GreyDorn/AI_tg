#!/usr/bin/env bash
# DE VPS: ensure vpoiskerabot.ru /ai-gpt/ proxies to MAX bot on RU VPS.
set -euo pipefail

RU_MAX_UPSTREAM="${RU_MAX_UPSTREAM:-http://195.133.73.52:8090}"
NGINX_SITE="${NGINX_SITE:-/etc/nginx/sites-available/vpoiskerabot.ru}"
MARKER="# MAX bot webhook proxy (managed by ensure-de-max-webhook-proxy.sh)"
NGINX_SCAN_DIRS="${NGINX_SCAN_DIRS:-/etc/nginx/sites-enabled /etc/nginx/sites-available /etc/nginx/conf.d /etc/nginx/snippets}"

if [[ ! -f "$NGINX_SITE" ]]; then
  echo "NGINX site not found: $NGINX_SITE"
  exit 1
fi

# Broken include of a deleted snippet causes 502 on /ai-gpt/.
sed -i.bak '/include\s\+.*ai-gpt.*\.conf/d' "$NGINX_SITE" 2>/dev/null || true

export NGINX_SITE MARKER RU_MAX_UPSTREAM NGINX_SCAN_DIRS

python3 - <<'PY'
import os
import re
from pathlib import Path

marker = os.environ["MARKER"]
upstream = os.environ["RU_MAX_UPSTREAM"].rstrip("/")
site_path = Path(os.environ["NGINX_SITE"])
scan_roots = [Path(p.strip()) for p in os.environ["NGINX_SCAN_DIRS"].split() if p.strip()]


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
        if is_ai_gpt_location_line(line):
            i = skip_brace_block(lines, i)
            removed += 1
            continue
        if re.search(r"^\s*include\s+[^\n]*ai-gpt[^\n]*;\s*$", line, re.I):
            removed += 1
            continue
        out.append(line)
        i += 1
    return "".join(out), removed


def is_ai_gpt_location_line(line: str) -> bool:
    stripped = line.strip()
    if stripped.startswith("#"):
        return False
    return bool(re.search(r"location\s+[^\n]*\/ai-gpt", line)) or (
        "location" in line and "/ai-gpt" in line
    )


def has_ai_gpt_location(text: str) -> bool:
    return any(is_ai_gpt_location_line(line) for line in text.splitlines())


def iter_nginx_configs() -> list[Path]:
    seen: set[Path] = set()
    out: list[Path] = []
    for root in scan_roots:
        if not root.exists():
            continue
        if root.is_file():
            candidates = [root]
        else:
            candidates = list(root.rglob("*"))
        for path in candidates:
            if not path.is_file():
                continue
            if path.suffix not in ("", ".conf"):
                continue
            try:
                real = path.resolve()
            except OSError:
                real = path
            if real in seen:
                continue
            seen.add(real)
            out.append(real)
    return out


def insert_managed_block(text: str) -> str:
    if marker in text and has_ai_gpt_location(text):
        # Already installed in this file.
        return text

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
    lines = text.splitlines(keepends=True)
    out: list[str] = []
    i = 0
    inserted = False
    while i < len(lines):
        line = lines[i]
        if (
            not inserted
            and re.search(r"server_name\b", line)
            and "vpoiskerabot.ru" in line
        ):
            out.append(line)
            i += 1
            while i < len(lines):
                out.append(lines[i])
                if lines[i].strip() == "{":
                    out.append("\n" + managed_block)
                    inserted = True
                    i += 1
                    break
                i += 1
            continue
        out.append(line)
        i += 1

    if not inserted:
        anchor = "    location ^~ /uploads/ {"
        joined = "".join(out)
        if anchor not in joined:
            raise SystemExit("Cannot insert /ai-gpt/ proxy (no server_name or /uploads/ anchor)")
        return joined.replace(anchor, managed_block + anchor, 1)
    return "".join(out)


for snippet in Path("/etc/nginx/snippets").glob("*ai-gpt*"):
    if snippet.is_file():
        print(f"Removing snippet file {snippet}")
        snippet.unlink()

config_files = iter_nginx_configs()
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
if has_ai_gpt_location(text) or re.search(r"include\s+[^\n]*ai-gpt", text, re.I):
    print("Remaining ai-gpt references in site file:")
    for n, ln in enumerate(text.splitlines(), 1):
        if "/ai-gpt" in ln or re.search(r"include\s+[^\n]*ai-gpt", ln, re.I):
            print(f"  {n}: {ln.rstrip()}")
    text, extra = strip_ai_gpt_blocks(text)
    if extra:
        print(f"Extra cleanup removed {extra} block(s) from {site_path}")
        site_path.write_text(text)
if has_ai_gpt_location(text) or re.search(r"include\s+[^\n]*ai-gpt", text, re.I):
    raise SystemExit(f"Still has /ai-gpt/ in {site_path} after cleanup")

text = insert_managed_block(text)
if not has_ai_gpt_location(text):
    raise SystemExit("Managed /ai-gpt/ block missing after insert")

# Exactly one active location in vpoiskerabot site file.
locs = [ln.strip() for ln in text.splitlines() if is_ai_gpt_location_line(ln)]
if len(locs) != 1:
    raise SystemExit(f"Expected 1 /ai-gpt/ location in {site_path}, found {len(locs)}: {locs}")

site_path.write_text(text)
print("Installed single /ai-gpt/ proxy →", upstream)

for cfg in iter_nginx_configs():
    if cfg == site_path.resolve():
        continue
    try:
        t = cfg.read_text()
    except OSError:
        continue
    if has_ai_gpt_location(t):
        raise SystemExit(f"Duplicate /ai-gpt/ location remains in {cfg}")
PY

if systemctl is-active max_ai_bot.service >/dev/null 2>&1; then
  echo "Stopping local max_ai_bot.service on DE (MAX runs on RU only)"
  systemctl stop max_ai_bot.service || true
  systemctl disable max_ai_bot.service || true
fi

echo "All /ai-gpt/ location directives under nginx:"
grep -Rn "location[^;]*\/ai-gpt" /etc/nginx/sites-enabled /etc/nginx/sites-available /etc/nginx/conf.d /etc/nginx/snippets 2>/dev/null || true

nginx -t
systemctl reload nginx

echo "Effective nginx /ai-gpt/ (must proxy to RU):"
nginx -T 2>/dev/null | grep -E "location.*ai-gpt|proxy_pass.*8090" || true

echo -n "RU upstream health: "
curl -sf --max-time 10 "${RU_MAX_UPSTREAM}/health" && echo || echo FAIL

echo -n "Public health: "
curl -sf --max-time 10 "https://vpoiskerabot.ru/ai-gpt/health" && echo || echo FAIL

grep -n "ai-gpt" "$NGINX_SITE" || true
