#!/usr/bin/env python3
"""run.py — general non-interactive adapter: one turn through run_turn for external
callers (shell scripts, Node, cron, other projects).

Unlike cli.py (the TUI, which runs THIS repo's persona in AGENT_DIR), run.py takes an
explicit --cwd + scoped --tool, so another project can use the engine with its OWN
directory, CLAUDE.md persona, and tools:

  echo "<prompt>" | run.py --cwd /path/to/project --tool Read --tool "Bash(node x.js:*)" --max-turns 15
  run.py "<prompt>" --cwd /path --remember mybot            # ← conversation memory

MEMORY — one system, everywhere (`--remember KEY`):
  Memory = keep one claude session per *conversation key* and resume it. Pass a stable
  key (a chat id, a thread name, anything) and successive turns with that key REMEMBER
  each other. OMIT --remember for stateless one-shots (e.g. cron jobs that must start
  fresh). Same key continues; a new key is fresh; `--forget KEY` clears it. The engine
  owns all the mechanics (load → resume → capture → save) — see agent.run_turn(remember=).

Prints Claude's output to stdout; on failure prints the reason to stderr and exits
non-zero so the caller can detect it.
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from agent import forget, run_turn  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("prompt", nargs="?", default="-", help="prompt; '-' or omitted = read stdin")
ap.add_argument("--cwd", default=os.getcwd(), help="run claude here (loads this dir's CLAUDE.md)")
ap.add_argument("--tool", action="append", default=[], help="an --allowedTools entry; repeatable")
ap.add_argument("--max-turns", type=int)
ap.add_argument("--timeout", type=int, help="seconds; run_turn kills claude on timeout")
ap.add_argument("--remember", metavar="KEY",
                help="conversation key (or path) — resume+persist memory across turns")
ap.add_argument("--forget", metavar="KEY", help="clear a conversation's memory and exit")
a = ap.parse_args()

if a.forget:
    sys.exit(0 if forget(a.forget) else 0)

prompt = sys.stdin.read() if a.prompt == "-" else a.prompt
extra = []
if a.tool:
    extra += ["--allowedTools", *a.tool]
if a.max_turns:
    extra += ["--max-turns", str(a.max_turns)]

try:
    out = run_turn(prompt, cwd=a.cwd, extra_args=extra, remember=a.remember, timeout=a.timeout)
except Exception as e:
    sys.stderr.write(f"run: {e}\n")
    sys.exit(1)

sys.stdout.write(out or "")
