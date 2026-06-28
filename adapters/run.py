#!/usr/bin/env python3
"""run.py — general non-interactive adapter: one turn through run_turn for external
callers (shell scripts, Node, cron, other projects).

Unlike cli.py (the TUI, which runs THIS repo's persona in AGENT_DIR), run.py takes an
explicit --cwd + scoped --tool, so another project can use the engine with its OWN
directory, CLAUDE.md persona, and tools:

  echo "<prompt>" | run.py --cwd /path/to/project --tool Read --tool "Bash(node x.js:*)" --max-turns 15
  run.py "<prompt>" --cwd /path --remember /path/state/session.txt    # ← conversation memory

MEMORY — the canonical pattern (`--remember FILE`):
  The ENGINE is stateless on purpose (a turn is a pure function). Memory is the
  ADAPTER's job, and this is the dead-simple, standard way to wire it: --remember reads
  a saved claude session id, `--resume`s it, and writes the new id back — so successive
  turns REMEMBER each other. OMIT --remember for stateless one-shots (e.g. cron jobs that
  must start fresh each run). Delete the FILE to clear the memory ("new conversation").

Prints Claude's output to stdout; on failure prints the reason to stderr and exits
non-zero so the caller can detect it.
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from agent import run_turn  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("prompt", nargs="?", default="-", help="prompt; '-' or omitted = read stdin")
ap.add_argument("--cwd", default=os.getcwd(), help="run claude here (loads this dir's CLAUDE.md)")
ap.add_argument("--tool", action="append", default=[], help="an --allowedTools entry; repeatable")
ap.add_argument("--max-turns", type=int)
ap.add_argument("--timeout", type=int, help="seconds; run_turn kills claude on timeout")
ap.add_argument("--remember", metavar="FILE",
                help="persist+resume a claude session here for conversation memory")
a = ap.parse_args()

prompt = sys.stdin.read() if a.prompt == "-" else a.prompt
extra = []
if a.tool:
    extra += ["--allowedTools", *a.tool]
if a.max_turns:
    extra += ["--max-turns", str(a.max_turns)]

session_id = None
if a.remember and os.path.isfile(a.remember):
    try:
        session_id = (open(a.remember).read().strip() or None)
    except OSError:
        session_id = None
if a.remember:
    # need claude's JSON envelope to read back the (possibly new) session id
    extra += ["--output-format", "json"]

try:
    out = run_turn(prompt, cwd=a.cwd, extra_args=extra, session_id=session_id, timeout=a.timeout)
except Exception as e:
    sys.stderr.write(f"run: {e}\n")
    sys.exit(1)

if a.remember:
    try:
        d = json.loads(out)
        sid = d.get("session_id")
        if sid:
            with open(a.remember, "w") as f:
                f.write(sid)
        out = d.get("result") or d.get("text") or ""
    except (ValueError, TypeError):
        pass  # not JSON — print raw
sys.stdout.write(out or "")
