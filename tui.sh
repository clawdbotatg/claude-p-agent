#!/usr/bin/env bash
# tui.sh — talk to your agent in a terminal.
#
#   ./tui.sh
#   echo "hi" | ./tui.sh
#
# Add other interfaces in adapters/ — see skills/extend/SKILL.md.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PY="${PYTHON:-python3}"

exec "$PY" "$HERE/adapters/cli.py" "$@"
