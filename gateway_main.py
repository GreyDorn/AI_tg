"""Entry point: venv/bin/python gateway_main.py"""

import asyncio

from gateway.app import main

if __name__ == "__main__":
    asyncio.run(main())
