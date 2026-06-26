#!/usr/bin/env python3
"""agent.py — the whole engine.

An agent here is just `claude -p` run in this directory, fed a message tagged
with a trust level. That's the entire idea. This file is the ~100 lines that
make it happen; everything else in the repo is config plugged into it.

A turn:
  1. pick a system prompt by trust level  (prompts/public.md | prompts/private.md)
  2. scrub the environment                (so the child runs on YOUR subscription)
  3. spawn `claude -p` with this dir as cwd → Claude Code auto-loads CLAUDE.md as persona
  4. hand back what it said

Adapters (terminal, web, voice, Telegram, …) are thin: they decide WHERE a
message came from and how much to trust it, then call run_turn(). They never
need to know anything about Claude.

Config via environment, or a `.env` file in the repo root (auto-loaded; real
environment variables take precedence). All optional — sensible defaults:
  AGENT_DIR        the agent's working dir / persona home   (default: this file's dir)
  BRAIN_DIRS       extra readable dirs, ':'-separated → --add-dir   (default: none)
  CLAUDE_BIN       path to the claude CLI                    (default: "claude")
  CLAUDE_ARGS      extra args for every turn, shell-split    (default: none)
  CLAUDE_ARGS_PUBLIC / CLAUDE_ARGS_PRIVATE   extra args per trust level
"""
import json
import os
import shlex
import subprocess
import sys
import threading

HERE = os.path.dirname(os.path.abspath(__file__))


def _load_env_file(path):
    """Minimal .env loader: `KEY=VALUE` lines → os.environ. No dependency, and a
    value already set in the real environment WINS (setdefault), so .env is a
    default, not an override. Without this, the .env the README tells you to
    create — including the CLAUDE_ARGS_PUBLIC trust-lock — would do nothing."""
    try:
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, _, val = line.partition("=")
                key = key.strip()
                val = val.strip().strip('"').strip("'")
                if key:
                    os.environ.setdefault(key, val)
    except FileNotFoundError:
        pass


_load_env_file(os.path.join(HERE, ".env"))

AGENT_DIR = os.path.abspath(os.environ.get("AGENT_DIR", HERE))
PROMPTS_DIR = os.path.join(HERE, "prompts")

VALID_TRUST = ("public", "private")

# ── the one non-obvious thing ────────────────────────────────────────────────
# If you shell `claude` from inside an environment that already has these set
# (e.g. you launched THIS process from Claude Code, or from another agent), the
# child detects it's "embedded" and switches to metered API billing with no
# transcript written. Scrubbing them makes the child a clean, top-level
# interactive-style run on your Claude subscription. Do not remove this.
SCRUB_PREFIXES = ("CLAUDECODE", "CLAUDE_CODE_")
SCRUB_EXACT = {"ANTHROPIC_API_KEY"}


def scrubbed_env():
    env = dict(os.environ)
    for k in list(env):
        if k in SCRUB_EXACT or any(k.startswith(p) for p in SCRUB_PREFIXES):
            env.pop(k, None)
    return env


def _read_prompt(trust):
    path = os.path.join(PROMPTS_DIR, f"{trust}.md")
    try:
        with open(path, encoding="utf-8") as f:
            return f.read().strip()
    except FileNotFoundError:
        return ""  # no per-channel prompt is fine; CLAUDE.md still carries persona


def _extra_args(trust):
    args = shlex.split(os.environ.get("CLAUDE_ARGS", ""))
    args += shlex.split(os.environ.get(f"CLAUDE_ARGS_{trust.upper()}", ""))
    return args


def run_turn(text, trust="private", on_event=None):
    """Run one agent turn. Returns the agent's reply as a string.

    `trust` selects the system prompt and any per-channel CLI flags. Keep the
    real security boundary in the CLI flags (--allowedTools / --permission-mode),
    not only in the prompt — see prompts/public.md.

    `on_event` makes the turn OBSERVABLE. Without it, `claude -p` prints only the
    final text — every tool call in between is invisible, so an adapter can show
    nothing but a spinner while the turn blocks. Pass a callback and we instead
    run with `--output-format stream-json` and hand you each event as it happens
    (system/init, assistant messages with text + tool_use blocks, tool_results,
    and the final result). That's the channel an adapter needs to narrate the
    work live — a line per action — instead of going dark then dumping. The
    return value is the same either way, so callers that don't care are unchanged.
    """
    if trust not in VALID_TRUST:
        raise ValueError(f"trust must be one of {VALID_TRUST}, got {trust!r}")

    cmd = [os.environ.get("CLAUDE_BIN", "claude"), "-p"]
    sys_prompt = _read_prompt(trust)
    if sys_prompt:
        cmd += ["--append-system-prompt", sys_prompt]
    for d in filter(None, os.environ.get("BRAIN_DIRS", "").split(":")):
        cmd += ["--add-dir", os.path.expanduser(d)]
    cmd += _extra_args(trust)

    if on_event is not None:
        # stream-json with -p requires --verbose; the flags compose fine with the
        # trust-lock args above (--allowedTools / --permission-mode etc.).
        return _run_streaming(
            cmd + ["--output-format", "stream-json", "--verbose", text], on_event
        )

    proc = subprocess.run(
        cmd + [text], cwd=AGENT_DIR, env=scrubbed_env(),
        capture_output=True, text=True,
    )
    if proc.returncode != 0:
        err = (proc.stderr or proc.stdout or "").strip()
        raise RuntimeError(f"claude exited {proc.returncode}: {err}")
    return proc.stdout.strip()


def _run_streaming(cmd, on_event):
    """Run `claude -p --output-format stream-json`, fire on_event(dict) per JSON
    line as it arrives, and return the final reply text. stderr is drained on a
    side thread so a chatty/erroring child can't deadlock the stdout read."""
    proc = subprocess.Popen(
        cmd, cwd=AGENT_DIR, env=scrubbed_env(), text=True, bufsize=1,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    )
    stderr_chunks = []
    err_thread = threading.Thread(
        target=lambda: stderr_chunks.extend(proc.stderr), daemon=True
    )
    err_thread.start()

    final = ""
    for line in proc.stdout:
        line = line.strip()
        if not line:
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue  # non-JSON noise on stdout — skip, never crash the turn
        if event.get("type") == "result":
            final = (event.get("result") or "").strip()
        try:
            on_event(event)
        except Exception:
            pass  # a rendering hiccup must never kill the turn

    proc.wait()
    err_thread.join(timeout=1)
    if proc.returncode != 0:
        err = "".join(stderr_chunks).strip()
        raise RuntimeError(f"claude exited {proc.returncode}: {err}")
    return final


if __name__ == "__main__":
    # Tiny one-shot for smoke-testing: `python3 agent.py [public|private] "message"`
    trust = "private"
    argv = sys.argv[1:]
    if argv and argv[0] in VALID_TRUST:
        trust, argv = argv[0], argv[1:]
    msg = " ".join(argv) or sys.stdin.read().strip()
    if not msg:
        sys.exit('usage: agent.py [public|private] "your message"')
    print(run_turn(msg, trust))
