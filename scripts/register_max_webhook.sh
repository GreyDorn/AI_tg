#!/usr/bin/env bash
# Register MAX webhook after deploy.
set -euo pipefail

cd "$(dirname "$0")/.."
source venv/bin/activate 2>/dev/null || true

python - <<'PY'
import asyncio
import os
from dotenv import load_dotenv
load_dotenv()
from max_bot.api import register_webhook, get_me

async def main():
    me = await get_me()
    print("MAX bot:", me)
    url = os.environ["MAX_WEBHOOK_URL"]
    secret = os.environ.get("MAX_WEBHOOK_SECRET", "")
    result = await register_webhook(url, secret)
    print("Webhook registered:", result)

asyncio.run(main())
PY
