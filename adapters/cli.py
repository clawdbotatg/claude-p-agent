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


USER_COLOR = "\033[36m"   # cyan — what you type
AGENT_COLOR = "\033[32m"  # green — what the agent says
RESET = "\033[0m"
DIM = "\033[90m"          # grey — the live activity log (one line per action)


class Spinner:
    """A braille spinner with live elapsed, drawn on the current line while a
    turn is in flight. The stream prints a line per tool call, but between those
    events the model is thinking with nothing to show — without this the terminal
    sits silent and you can't tell thinking from hung. The spinner fills that gap:
    it ticks on its own thread, and the renderer routes every printed line through
    `emit()` so the spinner is wiped clean just before a line lands, then redrawn
    underneath it. Only animates on a real tty; a no-op when piped so one-shot
    output stays clean. Use as a context manager."""

    FRAMES = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"

    def __init__(self, label="thinking", stream=sys.stdout):
        self.label = label
        self.stream = stream
        self.enabled = stream.isatty()
        self._lock = threading.Lock()  # serialize spinner draws against emit()
        self._stop = threading.Event()
        self._thread = None
        self._start = 0.0
        self._drawn = False  # is the spinner currently occupying the line?

    def _clear(self):
        if self._drawn:
            self.stream.write("\r\033[2K")  # carriage-return + erase line
            self._drawn = False

    def _spin(self):
        for frame in itertools.cycle(self.FRAMES):
            if self._stop.is_set():
                break
            elapsed = time.monotonic() - self._start
            with self._lock:
                if not self._stop.is_set():
                    self.stream.write(f"\r{DIM}{frame} {self.label}… {elapsed:4.1f}s{RESET}")
                    self.stream.flush()
                    self._drawn = True
            time.sleep(0.1)

    def emit(self, text):
        """Print a finished line through the spinner: wipe the spinner, write the
        line, and let the next tick redraw beneath it. Thread-safe."""
        with self._lock:
            self._clear()
            self.stream.write(text + "\n")
            self.stream.flush()

    def __enter__(self):
        if self.enabled:
            self._start = time.monotonic()
            self._thread = threading.Thread(target=self._spin, daemon=True)
            self._thread.start()
        return self

    def __exit__(self, *exc):
        self._stop.set()
        if self._thread:
            self._thread.join()
        if self.enabled:
            with self._lock:
                self._clear()
                self.stream.flush()
        return False


def summarize_tool(name, inp):
    """A short, human label for a tool call — the meat of each activity line.
    Picks the most identifying field per tool (the file, the command, the
    query) so the log reads `Read cli.py` / `Bash run tests`, not raw JSON."""
    inp = inp or {}
    if name == "Bash":
        return inp.get("description") or (inp.get("command", "").splitlines() or [""])[0]
    if name in ("Read", "Edit", "Write", "NotebookEdit"):
        path = inp.get("file_path") or inp.get("notebook_path") or ""
        return os.path.basename(path) or path
    if name in ("Grep", "Glob"):
        return inp.get("pattern", "")
    if name in ("Task", "Agent"):
        return inp.get("description") or inp.get("subagent_type", "")
    if name == "Skill":
        return inp.get("skill") or inp.get("command", "")
    if name == "WebFetch":
        return inp.get("url", "")
    if name == "WebSearch":
        return inp.get("query", "")
    if name == "TodoWrite":
        return "update todos"
    for k, v in inp.items():  # fallback: first field, truncated
        return f"{k}={str(v)[:50]}"
    return ""


def make_renderer(color, emit=print):
    """Build an on_event callback that prints the turn as it happens: a dim line
    per tool call, the agent's prose in green as each chunk arrives. Lines go out
    through `emit` (the Spinner's, on a tty) so each one wipes the live spinner
    before it lands. Returns (callback, state) where state['prose'] says whether
    any reply text printed — so the caller can fall back to printing the final
    string if the stream was silent (e.g. a turn that ended without a text block)."""
    dim, ac, rs = (DIM, AGENT_COLOR, RESET) if color else ("", "", "")
    start = time.monotonic()
    state = {"prose": False, "labeled": False}

    def on_event(ev):
        if ev.get("type") != "assistant":
            return
        elapsed = time.monotonic() - start
        for block in ev.get("message", {}).get("content", []):
            btype = block.get("type")
            if btype == "tool_use":
                name = block.get("name", "?")
                summ = summarize_tool(name, block.get("input"))
                tail = f"  {summ}" if summ else ""
                emit(f"{dim}  ⏺ {name}{tail}  ({elapsed:.1f}s){rs}")
            elif btype == "text":
                txt = block.get("text", "").strip()
                if not txt:
                    continue
                body = render_markdown(txt) if color else txt
                if not state["labeled"]:
                    emit(f"\n{ac}agent ›{rs} {body}")
                    state["labeled"] = True
                else:
                    emit(body)
                state["prose"] = True

    return on_event, state


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

    # Non-interactive (piped) input → one-shot, then exit. Guard it like the
    # interactive loop below: a piped turn must never dump a raw traceback on
    # ctrl-c, a closed downstream pipe, or a run_turn error.
    if not sys.stdin.isatty():
        msg = sys.stdin.read().strip()
        if msg:
            try:
                print(run_turn(msg, trust))
            except KeyboardInterrupt:  # ctrl-c mid-turn → abort cleanly, no traceback
                print(f"{DIM}  ⏹ turn aborted{RESET}", file=sys.stderr)
                sys.exit(130)
            except BrokenPipeError:  # downstream closed the pipe → leave quietly
                os._exit(0)  # skip the shutdown flush that would re-raise on the dead pipe
            except Exception as e:
                print(f"[error] {e}", file=sys.stderr)
                sys.exit(1)
        return

    # Only colorize on a real tty; piped/redirected output stays clean.
    color = sys.stdout.isatty()
    uc, ac, rs = (USER_COLOR, AGENT_COLOR, RESET) if color else ("", "", "")

    print(f"claude-p-agent · {trust} channel · ctrl-c stops a turn, ctrl-c again quits (or ctrl-d)")
    # One ctrl-c "stops the current thought"; a second one — with no real input
    # in between — quits. `armed` is that latch: set whenever a ctrl-c lands,
    # cleared the moment you type a real message, so the double-tap only quits
    # when it's a genuine repeat, not a stop-then-keep-going.
    armed = False
    while True:
        try:
            # Open the color before the prompt so the line you type is colored
            # too; reset right after so nothing else inherits it.
            msg = input(f"\n{uc}you › ").strip()
            sys.stdout.write(rs)
        except EOFError:  # ctrl-d → quit (as the banner says)
            sys.stdout.write(rs)
            print()
            return
        except KeyboardInterrupt:  # ctrl-c at the prompt
            sys.stdout.write(rs)
            if armed:  # second tap → quit
                print("^C")
                return
            print(f"^C  {DIM}(ctrl-c again to quit){rs}")
            armed = True
            continue
        armed = False  # a real message disarms the quit latch
        if not msg:
            continue
        try:
            # Stream the turn: a dim line per tool call, prose in green as it
            # lands — and a braille spinner ticking in the gaps while the model
            # thinks, so you watch the work happen and can always tell live from
            # hung. The renderer prints through the spinner's emit() so each line
            # wipes the spinner before it lands.
            with Spinner() as spin:
                emit = spin.emit if spin.enabled else print
                on_event, state = make_renderer(color, emit=emit)
                reply = run_turn(msg, trust, on_event=on_event)
            # Fallback: if the stream carried no assistant text (rare), still
            # show the final reply so a turn is never silent.
            if not state["prose"] and reply:
                body = render_markdown(reply) if color else reply
                print(f"\n{ac}agent ›{rs} {body}")
        except KeyboardInterrupt:  # ctrl-c mid-turn → stop the thought; arm quit
            print(f"\n{DIM}  ⏹ stopped  (ctrl-c again to quit){rs}")
            armed = True
        except Exception as e:
            print(f"\n[error] {e}", file=sys.stderr)


if __name__ == "__main__":
    main()
