"""Entry point: venv/bin/python max_main.py"""

import asyncio

from max_bot.app import main

if __name__ == "__main__":
    asyncio.run(main())
