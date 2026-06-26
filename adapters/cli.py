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
import itertools
import os
import sys
import threading
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from agent import run_turn  # noqa: E402


class Spinner:
    """A braille spinner on stderr while a turn runs. A turn is one blocking
    `subprocess.run`, so without this the terminal sits silent — you can't tell
    thinking from hung. Only animates on a real tty; a no-op otherwise so
    piped/one-shot output stays clean. Use as a context manager."""

    FRAMES = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"

    def __init__(self, label="thinking", stream=sys.stderr):
        self.label = label
        self.stream = stream
        self.enabled = stream.isatty()
        self._stop = threading.Event()
        self._thread = None

    def _spin(self):
        start = time.monotonic()
        for frame in itertools.cycle(self.FRAMES):
            if self._stop.is_set():
                break
            elapsed = time.monotonic() - start
            self.stream.write(f"\r\033[90m{frame} {self.label}… {elapsed:4.1f}s\033[0m")
            self.stream.flush()
            time.sleep(0.08)

    def __enter__(self):
        if self.enabled:
            self._thread = threading.Thread(target=self._spin, daemon=True)
            self._thread.start()
        return self

    def __exit__(self, *exc):
        self._stop.set()
        if self._thread:
            self._thread.join()
        if self.enabled:
            self.stream.write("\r\033[2K")  # erase the spinner line
            self.stream.flush()
        return False


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
            with Spinner():
                reply = run_turn(msg, trust)
            print(f"\nagent › {reply}")
        except Exception as e:
            print(f"\n[error] {e}", file=sys.stderr)


if __name__ == "__main__":
    main()
