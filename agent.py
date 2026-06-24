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

Config via environment (all optional — sensible defaults):
  AGENT_DIR        the agent's working dir / persona home   (default: this file's dir)
  BRAIN_DIRS       extra readable dirs, ':'-separated → --add-dir   (default: none)
  CLAUDE_BIN       path to the claude CLI                    (default: "claude")
  CLAUDE_ARGS      extra args for every turn, shell-split    (default: none)
  CLAUDE_ARGS_PUBLIC / CLAUDE_ARGS_PRIVATE   extra args per trust level
"""
import os
import shlex
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
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


def run_turn(text, trust="private"):
    """Run one agent turn. Returns the agent's reply as a string.

    `trust` selects the system prompt and any per-channel CLI flags. Keep the
    real security boundary in the CLI flags (--allowedTools / --permission-mode),
    not only in the prompt — see prompts/public.md.
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
    cmd += [text]

    proc = subprocess.run(
        cmd, cwd=AGENT_DIR, env=scrubbed_env(),
        capture_output=True, text=True,
    )
    if proc.returncode != 0:
        err = (proc.stderr or proc.stdout or "").strip()
        raise RuntimeError(f"claude exited {proc.returncode}: {err}")
    return proc.stdout.strip()


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
