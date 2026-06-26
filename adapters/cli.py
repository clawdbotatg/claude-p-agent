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
import re
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


USER_COLOR = "\033[36m"   # cyan — what you type
AGENT_COLOR = "\033[32m"  # green — what the agent says
RESET = "\033[0m"


def render_markdown(text):
    """Render the common markdown the agent emits to ANSI for a terminal.

    The agent replies in markdown; printed raw it shows literal `**`, `#`, and
    backticks. This is a deliberately small, stdlib-only renderer (the project
    has no deps) covering headers, bold/italic, inline + fenced code, and
    bullet/numbered lists — enough to read clean in a terminal. Anything it
    doesn't recognize passes through untouched, so it never mangles output.
    """
    B, I, C, H = "\033[1m", "\033[3m", "\033[96m", "\033[1m\033[4m"
    R = "\033[0m"

    def inline(s):
        s = re.sub(r"`([^`]+)`", lambda m: f"{C}{m.group(1)}{R}", s)          # `code`
        s = re.sub(r"\[([^\]]+)\]\((https?://[^)]+)\)",
                   lambda m: f"{m.group(1)} \033[2m{m.group(2)}{R}", s)        # [text](url)
        s = re.sub(r"\*\*([^*]+)\*\*", lambda m: f"{B}{m.group(1)}{R}", s)     # **bold**
        s = re.sub(r"(?<!\*)\*([^*]+)\*(?!\*)", lambda m: f"{I}{m.group(1)}{R}", s)  # *italic*
        return s

    out, in_fence = [], False
    for line in text.split("\n"):
        if line.lstrip().startswith("```"):
            in_fence = not in_fence
            continue
        if in_fence:
            out.append(f"{C}    {line}{R}")
            continue
        m = re.match(r"^(#{1,6})\s+(.*)", line)
        if m:
            out.append(f"{H}{inline(m.group(2))}{R}")
            continue
        m = re.match(r"^(\s*)[-*+]\s+(.*)", line)
        if m:
            out.append(f"{m.group(1)}• {inline(m.group(2))}")
            continue
        out.append(inline(line))
    return "\n".join(out)


def main():
    trust = "public" if "--public" in sys.argv[1:] else "private"

    # Non-interactive (piped) input → one-shot, then exit.
    if not sys.stdin.isatty():
        msg = sys.stdin.read().strip()
        if msg:
            print(run_turn(msg, trust))
        return

    # Only colorize on a real tty; piped/redirected output stays clean.
    color = sys.stdout.isatty()
    uc, ac, rs = (USER_COLOR, AGENT_COLOR, RESET) if color else ("", "", "")

    print(f"claude-p-agent · {trust} channel · ctrl-d to quit")
    while True:
        try:
            # Open the color before the prompt so the line you type is colored
            # too; reset right after so nothing else inherits it.
            msg = input(f"\n{uc}you › ").strip()
            sys.stdout.write(rs)
        except (EOFError, KeyboardInterrupt):
            sys.stdout.write(rs)
            print()
            return
        if not msg:
            continue
        try:
            with Spinner():
                reply = run_turn(msg, trust)
            # On a tty, render markdown to ANSI; the styling owns the body's
            # color, so only the label gets the agent green.
            body = render_markdown(reply) if color else reply
            print(f"\n{ac}agent ›{rs} {body}")
        except Exception as e:
            print(f"\n[error] {e}", file=sys.stderr)


if __name__ == "__main__":
    main()
