#!/usr/bin/env bash
# tg.sh — the short way to reach your agent from your phone.
#
# A thin launcher for the Telegram adapter (adapters/telegram.py), the sibling of
# ./tui.sh. It does nothing behaviorally — it just saves you typing `python3
# adapters/telegram.py` and runs from the repo root no matter where you call it.
#
#   ./tg.sh            # start the bot (reads TELEGRAM_BOT_TOKEN / _OWNER_ID from .env)
#
# First run prints setup steps if the token isn't configured yet. All args/env
# pass straight through to the adapter.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PY="${PYTHON:-python3}"

exec "$PY" "$HERE/adapters/telegram.py" "$@"
