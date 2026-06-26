#!/usr/bin/env bash
# tui.sh — the short way to talk to your agent in a terminal.
#
# A thin launcher for the hello-world terminal adapter (adapters/cli.py). It
# does nothing behaviorally — it just saves you typing `python3 adapters/cli.py`
# and runs from the repo root no matter where you call it from.
#
#   ./tui.sh                      # private REPL
#   ./tui.sh --public             # simulate an untrusted channel
#   AGENT_DIR=examples/builder ./tui.sh
#   echo "hi" | ./tui.sh          # one-shot via stdin
#
# All args/stdin/env pass straight through to the adapter.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PY="${PYTHON:-python3}"

exec "$PY" "$HERE/adapters/cli.py" "$@"
