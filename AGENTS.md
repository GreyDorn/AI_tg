# AGENTS.md

## Cursor Cloud specific instructions

This repo is a single Python service: a Telegram AI chat + image bot (`aiogram` long-polling) backed by an embedded SQLite file (`bot.db`). There is no web UI, no separate DB server, and no message queue.

### Environment
- Python 3.12 with a virtualenv at `venv/` (gitignored). The update script creates it and installs `requirements.txt`. Always run via `venv/bin/python` (or activate `venv`).
- Config is read from `.env` (gitignored, loaded by `config.py` via `python-dotenv`). Copy from `.env.example`. `DATABASE_URL` is hardcoded in `config.py` (not env-driven).

### Run / build / lint / test
- Run (dev): `venv/bin/python main.py`. It auto-creates/migrates `bot.db` on startup, probes OpenRouter, then starts long polling.
- Build: none (interpreted Python, no build step).
- Lint: none configured in this repo.
- Tests: no test suite exists. To smoke-test the data layer, call the async helpers in `db/repository.py` (e.g. `init_db`, `get_or_create_user`, `spend_credits`, `process_subscription_payment`, `get_bot_stats`).

### Gotchas
- `main.py` raises `ValueError` if `BOT_TOKEN` is empty. With any well-formed-but-fake token the app still boots through DB init + OpenRouter probe and only fails at the first Telegram `get_me()` call (401). That sequence is the expected "boots correctly, just no valid token" signal.
- Real end-to-end use (actually chatting / generating images in Telegram) requires secrets: a real `BOT_TOKEN` from @BotFather and at least one LLM key (default chat model is Groq's `llama-3.3-70b`, so `GROQ_API_KEY` is the simplest). Image generation via `flux-free`/`turbo-free` (Pollinations) needs no key.
- `scripts/*.sh`, `deploy/`, and `.github/workflows/deploy.yml` are production deployment only (systemd + rsync/SSH) — not for local dev.
