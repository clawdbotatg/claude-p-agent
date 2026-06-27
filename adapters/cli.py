#!/usr/bin/env python3
"""cli.py — terminal adapter: talk to your agent in a TUI.

Maps keyboard input → run_turn(). Add other front-ends as sibling scripts in
adapters/ (Telegram, web, etc.) — see skills/extend/SKILL.md.

  python3 adapters/cli.py             # interactive REPL
  echo "hi" | python3 adapters/cli.py # one-shot via stdin
"""
import codecs
import itertools
import os
import re
import shutil
import sys
import threading
import time

try:  # POSIX-only; the raw-mode editor falls back to input() without these.
    import termios
    import tty
except ImportError:  # pragma: no cover — non-POSIX
    termios = tty = None

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from agent import AGENT_DIR, agent_home, run_turn  # noqa: E402

REPO_ROOT = agent_home()
EXAMPLE_PATH = os.path.join(REPO_ROOT, "CLAUDE.md.example")
CLAUDE_PATH = os.path.join(AGENT_DIR, "CLAUDE.md")
NAME_PLACEHOLDER = "<AGENT NAME>"

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
    """Build an on_event callback: dim lines per tool call; agent prose rendered
    once when the full reply is known (markdown → ANSI). Returns (callback, state)."""
    dim, ac, rs = (DIM, AGENT_COLOR, RESET) if color else ("", "", "")
    start = time.monotonic()
    state = {"prose": False, "text": "", "displayed": False}

    def _show_prose(text):
        text = text.strip()
        if not text or state["displayed"]:
            return
        body = render_markdown(text) if color else text
        emit(f"\n{ac}agent ›{rs} {body}")
        state["displayed"] = True
        state["prose"] = True
        state["text"] = text

    def on_event(ev):
        etype = ev.get("type")
        if etype == "stream_event":
            inner = ev.get("event", {})
            if inner.get("type") == "content_block_delta":
                delta = inner.get("delta", {})
                if delta.get("type") == "text_delta" and delta.get("text"):
                    state["text"] += delta["text"]
                    state["prose"] = True
            return
        if etype != "assistant":
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
                txt = block.get("text", "")
                if txt.strip():
                    _show_prose(txt)

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


_ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")


def _vis_len(s):
    """Visible width of a string — its length with SGR color codes stripped,
    so the prompt's color escapes don't throw off cursor math."""
    return len(_ANSI_RE.sub("", s))


def _enter_kind(seq):
    """Classify a CSI sequence that encodes the Enter key, so we can tell a
    bare Enter (submit) from a modified one (Shift/Alt/Ctrl+Enter → newline).

    Two terminal encodings report this once their protocol is enabled:
      • kitty keyboard protocol  → CSI `13[;mods]u`   (e.g. `13;2u`)
      • xterm modifyOtherKeys    → CSI `27;mods;13~`
    The keycode for Enter is 13; the modifier field is 1 + a bitmask, so any
    value > 1 means a modifier was held. Returns "newline", "submit", or None.
    """
    if seq.endswith("u"):                       # kitty: <code>[;<mods>]u
        parts = seq[:-1].split(";")
        if not parts[0].isdigit() or int(parts[0]) != 13:
            return None
        mods = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else 1
        return "newline" if mods > 1 else "submit"
    if seq.endswith("~") and seq.startswith("27;"):  # modifyOtherKeys: 27;<mods>;<code>~
        parts = seq[:-1].split(";")
        if len(parts) >= 3 and parts[2].isdigit() and int(parts[2]) == 13:
            mods = int(parts[1]) if parts[1].isdigit() else 1
            return "newline" if mods > 1 else "submit"
    return None


def read_multiline(prompt, cont, reset):
    """Read one submission from the terminal — Enter submits, Shift/Alt+Enter
    inserts a newline, and a paste lands as a single unit.

    `input()` returns at the first newline, so a pasted multiline message left
    its tail in stdin to be read back as separate prompts on later calls — the
    bug this replaces. Here we drive the tty in raw mode and own newline handling
    ourselves: a literal Enter is the only thing that submits. Bracketed paste
    (DECSET 2004) wraps a paste in markers so its embedded newlines are inserted,
    never submitted. Shift+Enter (often LF / 0x0A on macOS and Cursor), modifyOtherKeys
    CSI `27;2;13~`, kitty CSI-u `13;2u` if present, and Alt/ESC+Enter add a newline.

    The cursor always sits at the end of the buffer — there's no mid-line editing
    beyond backspace — which keeps the redraw honest: we count the rows the block
    occupies (accounting for wrap), jump back to the top, clear, and reprint.

    Raises KeyboardInterrupt on ctrl-c and EOFError on ctrl-d at an empty buffer,
    matching what the caller already expects from input(). Falls back to input()
    when there's no real tty or termios isn't available."""
    if termios is None or not sys.stdin.isatty():
        return input(prompt)

    fd = sys.stdin.fileno()
    out = sys.stdout
    buf = []           # the message so far, as a list of chars (incl. '\n')
    rows = [None]      # rows the last render occupied (None until first draw)
    dec = codecs.getincrementaldecoder("utf-8")()

    def render():
        # Lay the buffer out as display segments: prompt + first line, then the
        # continuation marker before each subsequent line.
        lines = "".join(buf).split("\n")
        segs = [prompt + lines[0]] + [cont + ln for ln in lines[1:]]
        w = max(1, shutil.get_terminal_size((80, 24)).columns)

        chunk = []
        if rows[0] is not None:  # return to the top of the previous block, clear it
            chunk.append("\r")
            if rows[0] > 1:
                chunk.append(f"\x1b[{rows[0] - 1}A")
            chunk.append("\x1b[J")
        chunk.append("\r\n".join(segs))  # raw mode: \n alone won't return the carriage
        out.write("".join(chunk))
        out.flush()

        # Count rows the block now spans, so the next render knows how far up to
        # jump. Each segment wraps every `w` columns (pending-wrap aware).
        total = 0
        for i, ln in enumerate(lines):
            vis = _vis_len(prompt if i == 0 else cont) + len(ln)
            total += 1 + (max(vis, 1) - 1) // w
        rows[0] = total

    def read_csi():
        # Consume a CSI sequence after ESC[ up to and including its final byte.
        seq = b""
        while True:
            b = os.read(fd, 1)
            if not b:
                break
            seq += b
            if 0x40 <= b[0] <= 0x7E:
                break
        return seq.decode("latin1")

    def read_paste():
        # Slurp a bracketed paste until the ESC[201~ terminator; normalize CRLF.
        data = b""
        while True:
            b = os.read(fd, 1)
            if not b:
                break
            data += b
            if data.endswith(b"\x1b[201~"):
                data = data[:-6]
                break
        return data.decode("utf-8", "replace").replace("\r\n", "\n").replace("\r", "\n")

    out.write("\n")  # the blank separator line, drawn while still in cooked mode
    out.flush()
    old = termios.tcgetattr(fd)
    # Turn on the input modes we depend on. A terminal that doesn't understand
    # any of these ignores the sequence (it's an unknown CSI), so this is safe
    # everywhere:
    #   ?2004h  bracketed paste — a paste's embedded newlines never submit
    #   >4;1m   xterm modifyOtherKeys — Shift+Enter as CSI `27;2;13~`
    # Do NOT enable kitty keyboard protocol (>1u): on terminals that honor it,
    # *every* key becomes a CSI-u sequence, and we only decode a few — typing
    # would silently break. Shift+Enter is covered by LF (0x0A) on macOS/Cursor
    # and by modifyOtherKeys / Alt+Enter elsewhere.
    out.write("\x1b[?2004h\x1b[>4;1m")
    out.flush()
    try:
        tty.setraw(fd)
        render()
        while True:
            b = os.read(fd, 1)
            if not b:  # stdin closed
                raise EOFError
            c = b[0]
            if c == 0x03:  # ctrl-c
                out.write("\r\n")
                raise KeyboardInterrupt
            if c == 0x04:  # ctrl-d → EOF only on an empty buffer
                if not buf:
                    out.write("\r\n")
                    raise EOFError
                continue
            if c in (0x7F, 0x08):  # backspace / delete
                if buf:
                    buf.pop()
                    render()
                continue
            if c == 0x0A:  # LF — Shift+Enter on many terminals (macOS, iTerm, Cursor)
                buf.append("\n")
                render()
                continue
            if c == 0x0D:  # CR — bare Enter → submit everything as one prompt
                out.write(reset + "\r\n")
                out.flush()
                return "".join(buf)
            if c == 0x1B:  # ESC — start of an escape sequence
                nb = os.read(fd, 1)
                if not nb:
                    continue
                if nb[0] == 0x5B:  # '['
                    seq = read_csi()
                    if seq == "200~":
                        buf.extend(read_paste())
                        render()
                    else:
                        kind = _enter_kind(seq)  # Shift/Alt/Ctrl+Enter via CSI
                        if kind == "newline":
                            buf.append("\n")
                            render()
                        elif kind == "submit":  # a terminal that reports bare Enter as CSI-u
                            out.write(reset + "\r\n")
                            out.flush()
                            return "".join(buf)
                        # arrows and other CSI sequences: ignored
                elif nb[0] in (0x0D, 0x0A):  # Alt/ESC+Enter → newline
                    buf.append("\n")
                    render()
                continue
            ch = dec.decode(b)  # printable (may be multi-byte UTF-8)
            if ch:
                add = [k for k in ch if k.isprintable()]
                if add:
                    buf.extend(add)
                    render()
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old)
        # Undo every mode we enabled above, in reverse, so the next program
        # (or the turn's own output) inherits a clean terminal.
        out.write("\x1b[>4;0m\x1b[?2004l")
        out.flush()


def _claude_md_needs_setup():
    if not os.path.isfile(CLAUDE_PATH):
        return True
    try:
        with open(CLAUDE_PATH, encoding="utf-8") as f:
            return NAME_PLACEHOLDER in f.read()
    except OSError:
        return True


def personalize_claude_md(text, name):
    """Fill the template with a chosen agent name and minimal starter persona."""
    name = name.strip()
    text = text.replace(NAME_PLACEHOLDER, name)
    text = text.replace(
        "TODO: one short paragraph — who you are and what you're for.",
        f"You help your owner on their computer — practical, capable, and direct.",
        1,
    )
    text = text.replace(
        "TODO: tone, length, formatting.",
        "Friendly and concise. Plain text.",
        1,
    )
    return text


def bootstrap_claude_md(*, interactive):
    """First run: create CLAUDE.md from the example and ask what to call the agent."""
    if not _claude_md_needs_setup():
        return None
    if not os.path.isfile(EXAMPLE_PATH):
        raise RuntimeError(f"missing template: {EXAMPLE_PATH}")
    with open(EXAMPLE_PATH, encoding="utf-8") as f:
        template = f.read()
    if interactive and sys.stdin.isatty():
        print("First run — set up your agent.")
        while True:
            try:
                name = input("What should I be called? › ").strip()
            except (EOFError, KeyboardInterrupt):
                print()
                sys.exit(0)
            if name:
                break
            print("  (need a name — try again)")
    else:
        name = "agent"
    body = personalize_claude_md(template, name)
    with open(CLAUDE_PATH, "w", encoding="utf-8") as f:
        f.write(body)
    return name


def main():
    # Non-interactive (piped) input → one-shot, then exit. Guard it like the
    # interactive loop below: a piped turn must never dump a raw traceback on
    # ctrl-c, a closed downstream pipe, or a run_turn error.
    if not sys.stdin.isatty():
        try:
            bootstrap_claude_md(interactive=False)
        except Exception as e:
            print(f"[error] {e}", file=sys.stderr)
            sys.exit(1)
        msg = sys.stdin.read().strip()
        if msg:
            try:
                print(run_turn(msg))
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

    try:
        name = bootstrap_claude_md(interactive=True)
    except Exception as e:
        print(f"[error] {e}", file=sys.stderr)
        sys.exit(1)
    if name:
        print(f"{DIM}  wrote {CLAUDE_PATH} — hi, I'm {name}.{rs}")

    print("claude-p-agent · ctrl-c stops a turn, ctrl-c again quits (or ctrl-d)")
    if sys.stdin.isatty():
        print(f"{DIM}  shift+enter (or alt+enter) for a new line · enter to send{rs}")
    # One ctrl-c "stops the current thought"; a second one — with no real input
    # in between — quits. `armed` is that latch: set whenever a ctrl-c lands,
    # cleared the moment you type a real message, so the double-tap only quits
    # when it's a genuine repeat, not a stop-then-keep-going.
    armed = False
    while True:
        try:
            # Open the color before the prompt so the text you type is colored
            # too; the editor writes the reset when you submit. The editor owns
            # newline handling — Enter submits, shift+enter inserts a line — so a
            # pasted multiline message arrives as ONE prompt, not one per line.
            msg = read_multiline(f"{uc}you › ", f"{DIM}    … {uc}", rs).strip()
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
                reply = run_turn(msg, on_event=on_event)
            if not state["displayed"] and (reply or state["text"]).strip():
                body = render_markdown(reply.strip()) if color else reply.strip()
                print(f"\n{ac}agent ›{rs} {body}")
        except KeyboardInterrupt:  # ctrl-c mid-turn → stop the thought; arm quit
            print(f"\n{DIM}  ⏹ stopped  (ctrl-c again to quit){rs}")
            armed = True
        except Exception as e:
            print(f"\n[error] {e}", file=sys.stderr)


if __name__ == "__main__":
    main()
