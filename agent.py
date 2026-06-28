#!/usr/bin/env python3
"""agent.py — the whole engine.

An agent is `claude -p` run in a directory (AGENT_DIR), with an optional extra
system prompt from the adapter. That's the entire idea.

A turn:
  1. scrub the environment          (child runs on YOUR subscription, not metered API)
  2. spawn `claude -p` in AGENT_DIR → Claude Code auto-loads CLAUDE.md as persona
  3. optionally append adapter-supplied channel policy
  4. hand back what it said

Adapters decide WHERE a message came from and what extra prompt/CLI flags to
pass. The engine does not know about public/private, voice, or backchannel.

Config via `.env` in the repo root (auto-loaded; real env wins):
  AGENT_DIR      persona home / cwd for claude -p     (default: this file's dir)
  BRAIN_DIRS     extra readable dirs, ':'-separated   (→ --add-dir)
  CLAUDE_BIN     path to claude CLI                   (default: "claude")
  CLAUDE_ARGS     extra CLI args every turn, shell-split
"""
import json
import os
import re
import shlex
import subprocess
import sys
import threading

HERE = os.path.dirname(os.path.abspath(__file__))


def agent_home():
    """Root of the claude-p-agent install (for imports from other repos)."""
    return os.environ.get("CLAUDE_P_AGENT_HOME", HERE)


def _load_env_file(path):
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


_load_env_file(os.path.join(agent_home(), ".env"))

AGENT_DIR = os.path.abspath(os.environ.get("AGENT_DIR", agent_home()))

# ── the one non-obvious thing ────────────────────────────────────────────────
# If you shell `claude` from inside an environment that already has these set,
# the child detects "embedded" mode → metered API billing, no transcript.
SCRUB_PREFIXES = ("CLAUDECODE", "CLAUDE_CODE_")
SCRUB_EXACT = {"ANTHROPIC_API_KEY", "AI_AGENT"}


def scrubbed_env():
    env = dict(os.environ)
    for k in list(env):
        if k in SCRUB_EXACT or any(k.startswith(p) for p in SCRUB_PREFIXES):
            env.pop(k, None)
    return env


def read_prompt(path):
    """Read a prompt file. Adapters own the paths."""
    with open(path, encoding="utf-8") as f:
        return f.read().strip()


def _base_extra_args():
    return shlex.split(os.environ.get("CLAUDE_ARGS", ""))


def _build_flags(
    *,
    append_system_prompt=None,
    session_id=None,
    add_dirs=None,
    extra_args=None,
    stream=False,
):
    """CLI flags for `claude -p`. Prompt goes immediately after `-p` (see _claude_cmd)."""
    flags = []
    if append_system_prompt:
        flags += ["--append-system-prompt", append_system_prompt]
    for d in add_dirs or []:
        flags += ["--add-dir", os.path.expanduser(d)]
    for d in filter(None, os.environ.get("BRAIN_DIRS", "").split(":")):
        flags += ["--add-dir", os.path.expanduser(d)]
    flags += _base_extra_args()
    if extra_args:
        flags += list(extra_args)
    if session_id:
        flags += ["--resume", session_id]
    if stream:
        flags += ["--output-format", "stream-json", "--verbose", "--include-partial-messages"]
    return flags


def _claude_cmd(text, flags, input_via="argv"):
    """Assemble argv. Newer claude requires the prompt right after `-p` when flags
    like --add-dir follow — a trailing positional prompt is ignored."""
    bin_ = os.environ.get("CLAUDE_BIN", "claude")
    if input_via == "argv":
        return [bin_, "-p", text] + flags
    return [bin_, "-p"] + flags


# ── memory ───────────────────────────────────────────────────────────────────
# ONE system, everywhere: a turn "remembers" by keeping a single claude session_id
# per *conversation key* and `--resume`-ing it. The engine owns the whole mechanic —
# load the key's id, resume, capture the new id, save it back — so no adapter ever
# hand-rolls session juggling again. Pass `remember=<key>` to run_turn (or omit for a
# stateless one-shot). Same key continues; new key is fresh; forget(key) resets.

def _memory_root():
    return os.path.abspath(os.path.expanduser(
        os.environ.get("CLAUDE_P_AGENT_MEMORY") or os.path.join(agent_home(), ".memory")
    ))


def _memory_path(key):
    """A conversation key → the file holding its session id. A key that looks like a
    path (has a separator) is used as-is so a caller can pin the location; a plain
    name is stored in the engine-owned memory dir."""
    key = str(key)
    if "/" in key or os.sep in key:
        return os.path.abspath(os.path.expanduser(key))
    safe = re.sub(r"[^A-Za-z0-9._-]", "_", key).strip("._") or "default"
    return os.path.join(_memory_root(), safe + ".session")


def _read_session(path):
    try:
        with open(path, encoding="utf-8") as f:
            return f.read().strip() or None
    except OSError:
        return None


def _write_session(path, sid):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(sid)


def _parse_json_result(raw):
    """claude --output-format json → (reply_text, session_id)."""
    try:
        d = json.loads(raw)
    except (ValueError, TypeError):
        return raw, None
    if isinstance(d, dict):
        return (d.get("result") or "").strip(), d.get("session_id")
    return raw, None


def forget(key):
    """Clear one conversation's memory. Returns True if anything was removed."""
    try:
        os.remove(_memory_path(key))
        return True
    except OSError:
        return False


def run_turn(
    text,
    *,
    append_system_prompt=None,
    session_id=None,
    cwd=None,
    add_dirs=None,
    extra_args=None,
    on_event=None,
    input_via="argv",
    return_meta=False,
    proc_holder=None,
    timeout=None,
    remember=None,
):
    """Run one agent turn.

    `append_system_prompt` — channel policy from the adapter (engine has none).
    `remember` — conversation key (or path); when set, the engine loads that
        conversation's stored session id, `--resume`s it, and saves the new id back,
        so successive turns with the same key remember each other. Omit for a
        stateless one-shot. `session_id` (if passed) overrides the stored id.
    `on_event` — if set, run stream-json and fire the callback per event.
    `input_via` — \"argv\" (default) or \"stdin\" (prompt written to stdin).
    `return_meta` — if True, return {\"text\", \"session_id\"}; else return str.
    `proc_holder` — if a dict, filled with {\"proc\": Popen} for streaming turns (abort).
    """
    workdir = os.path.abspath(cwd or AGENT_DIR)
    stream = on_event is not None
    extra_args = list(extra_args or [])

    mem_path = _memory_path(remember) if remember else None
    if mem_path and session_id is None:
        session_id = _read_session(mem_path)
    # A blocking turn can't report the new id through stream events, so ask claude
    # for its JSON envelope and parse the id out. This wart lives here, once, not in
    # every adapter.
    capture_blocking = bool(remember) and not stream
    if capture_blocking and "--output-format" not in extra_args:
        extra_args += ["--output-format", "json"]

    flags = _build_flags(
        append_system_prompt=append_system_prompt,
        session_id=session_id,
        add_dirs=add_dirs,
        extra_args=extra_args,
        stream=stream,
    )
    cmd = _claude_cmd(text, flags, input_via=input_via)

    meta = {"session_id": session_id}

    def _track_session(event):
        if event.get("type") == "system" and event.get("subtype") == "init":
            sid = event.get("session_id")
            if sid:
                meta["session_id"] = sid
        elif event.get("type") == "result" and event.get("session_id"):
            meta["session_id"] = event["session_id"]

    if stream:
        final = _run_streaming(
            cmd, text, workdir, on_event, _track_session,
            input_via=input_via, proc_holder=proc_holder,
        )
    else:
        raw = _run_blocking(
            cmd, text, workdir, input_via=input_via, timeout=timeout,
        )
        if capture_blocking:
            final, sid = _parse_json_result(raw)
            if sid:
                meta["session_id"] = sid
        else:
            final = raw

    if mem_path and meta["session_id"]:
        _write_session(mem_path, meta["session_id"])

    if return_meta:
        return {"text": final, "session_id": meta["session_id"]}
    return final


def _run_blocking(cmd, text, cwd, input_via="argv", timeout=None):
    env = scrubbed_env()
    try:
        if input_via == "stdin":
            proc = subprocess.run(
                cmd, cwd=cwd, env=env, input=text, capture_output=True, text=True,
                timeout=timeout,
            )
        else:
            proc = subprocess.run(
                cmd, cwd=cwd, env=env, capture_output=True, text=True,
                timeout=timeout, stdin=subprocess.DEVNULL,
            )
    except subprocess.TimeoutExpired:
        raise RuntimeError(f"claude timed out after {timeout}s")
    if proc.returncode != 0:
        err = (proc.stderr or proc.stdout or "").strip()
        raise RuntimeError(f"claude exited {proc.returncode}: {err}")
    return proc.stdout.strip()


def _run_streaming(cmd, text, cwd, on_event, track_session, input_via="argv",
                   proc_holder=None):
    env = scrubbed_env()
    proc = subprocess.Popen(
        cmd, cwd=cwd, env=env, text=True, bufsize=1,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        stdin=subprocess.PIPE if input_via == "stdin" else subprocess.DEVNULL,
    )
    if proc_holder is not None:
        proc_holder["proc"] = proc
    if input_via == "stdin":
        proc.stdin.write(text)
        proc.stdin.close()

    stderr_chunks = []
    err_thread = threading.Thread(
        target=lambda: stderr_chunks.extend(proc.stderr), daemon=True
    )
    err_thread.start()

    final = ""
    try:
        for line in proc.stdout:
            line = line.strip()
            if not line:
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            if event.get("type") == "result":
                final = (event.get("result") or "").strip()
            track_session(event)
            try:
                on_event(event)
            except Exception:
                pass
        proc.wait()
    except KeyboardInterrupt:
        proc.terminate()
        try:
            proc.wait(timeout=2)
        except subprocess.TimeoutExpired:
            proc.kill()
        raise
    finally:
        err_thread.join(timeout=1)
    if proc.returncode != 0:
        err = "".join(stderr_chunks).strip()
        raise RuntimeError(f"claude exited {proc.returncode}: {err}")
    return final


if __name__ == "__main__":
    argv = sys.argv[1:]
    append = None
    if argv and argv[0] == "--append-file":
        append = read_prompt(argv[1])
        argv = argv[2:]
    msg = " ".join(argv) or sys.stdin.read().strip()
    if not msg:
        sys.exit('usage: agent.py [--append-file PATH] "your message"')
    try:
        print(run_turn(msg, append_system_prompt=append))
    except KeyboardInterrupt:
        print("\n  ⏹ turn aborted", file=sys.stderr)
        sys.exit(130)
    except Exception as e:
        print(f"[error] {e}", file=sys.stderr)
        sys.exit(1)
