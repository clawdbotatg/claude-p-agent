#!/usr/bin/env python3
"""cli.py — the hello-world adapter: talk to your agent in a terminal.

An adapter's whole job is to decide (a) WHERE a message came from and (b) how
much to trust it, then call run_turn(text, trust). That's all an adapter is.
This one reads lines from your terminal — so it defaults to `private` (you're at
your own keyboard). Pass --public to feel the untrusted-channel behavior.

  python3 adapters/cli.py             # private REPL
  python3 adapters/cli.py --public    # simulate an untrusted channel
  echo "hi" | python3 adapters/cli.py # one-shot via stdin
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from agent import run_turn  # noqa: E402


def main():
    trust = "public" if "--public" in sys.argv[1:] else "private"

    # Non-interactive (piped) input → one-shot, then exit.
    if not sys.stdin.isatty():
        msg = sys.stdin.read().strip()
        if msg:
            print(run_turn(msg, trust))
        return

    print(f"claude-p-agent · {trust} channel · ctrl-d to quit")
    while True:
        try:
            msg = input("\nyou › ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return
        if not msg:
            continue
        try:
            print(f"\nagent › {run_turn(msg, trust)}")
        except Exception as e:
            print(f"\n[error] {e}", file=sys.stderr)


if __name__ == "__main__":
    main()
