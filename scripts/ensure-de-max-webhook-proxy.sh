#!/usr/bin/env bash
# DE VPS: vpoiskerabot.ru → proxy /ai-gpt/ to MAX bot on RU VPS (8090).
set -euo pipefail

RU_MAX_UPSTREAM="${RU_MAX_UPSTREAM:-http://195.133.73.52:8090}"
NGINX_SITE="${NGINX_SITE:-/etc/nginx/sites-available/vpoiskerabot.ru}"
MARKER="# MAX bot webhook proxy (managed by ensure-de-max-webhook-proxy.sh)"

if [[ ! -f "$NGINX_SITE" ]]; then
  echo "NGINX site not found: $NGINX_SITE"
  exit 1
fi

if grep -qF "$MARKER" "$NGINX_SITE"; then
  echo "MAX webhook proxy block already present"
else
  tmp="$(mktemp)"
  awk -v block="$MARKER" -v upstream="$RU_MAX_UPSTREAM" '
    /server_name vpoiskerabot.ru;/ { in_main=1 }
    in_main && /location \^~ \/uploads\// && !inserted {
      print "    " block
      print "    location ^~ /ai-gpt/ {"
      print "        proxy_pass " upstream "/;"
      print "        proxy_http_version 1.1;"
      print "        proxy_set_header Host $host;"
      print "        proxy_set_header X-Real-IP $remote_addr;"
      print "        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;"
      print "        proxy_set_header X-Forwarded-Proto $scheme;"
      print "        proxy_set_header X-Max-Bot-Api-Secret $http_x_max_bot_api_secret;"
      print "        proxy_read_timeout 300s;"
      print "        proxy_send_timeout 300s;"
      print "    }"
      print ""
      inserted=1
    }
    { print }
  ' "$NGINX_SITE" > "$tmp"
  cp "$tmp" "$NGINX_SITE"
  rm -f "$tmp"
  echo "Inserted MAX webhook proxy into $NGINX_SITE"
fi

nginx -t
systemctl reload nginx

echo -n "RU MAX health via DE public URL: "
curl -sf --max-time 10 "https://vpoiskerabot.ru/ai-gpt/health" || echo FAIL

echo -n "RU MAX direct from DE: "
curl -sf --max-time 10 "${RU_MAX_UPSTREAM}/health" || echo FAIL
