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


def _child_env(auto_memory=True):
    # The scrub above eats every CLAUDE_CODE_* var — including a user's own
    # CLAUDE_CODE_DISABLE_AUTO_MEMORY — so the opt-out has to be re-injected here.
    env = scrubbed_env()
    if not auto_memory:
        env["CLAUDE_CODE_DISABLE_AUTO_MEMORY"] = "1"
    _route_subscription(env)
    return env


# ── subscription router (built in, on by default) ────────────────────────────
# If this box holds multiple Claude subscription logins — one config dir per
# plan under ~/.clawd-accounts/<name>, each signed in ONCE via
#   CLAUDE_CONFIG_DIR=~/.clawd-accounts/<name> claude /login
# (the clawd-harness accounts page manages these) — then every turn runs on
# the plan with the MOST HEADROOM right now. Usage comes from Claude's OAuth
# usage endpoint (undocumented: every failure degrades to "don't route"),
# cached for CLAUDE_P_ROUTER_TTL seconds. The plain ~/.claude login
# participates as `default`. An operator-set CLAUDE_CONFIG_DIR always wins
# (explicit pin > router). Boxes with no account dirs behave exactly as
# before. Disable with CLAUDE_P_ROUTER=0.
ROUTER_ON = os.environ.get("CLAUDE_P_ROUTER", "1") != "0"
ROUTER_TTL = float(os.environ.get("CLAUDE_P_ROUTER_TTL", "600"))
ACCOUNTS_DIR = os.path.expanduser(
    os.environ.get("CLAWD_ACCOUNTS_DIR", "~/.clawd-accounts"))
OAUTH_CLIENT_ID = "9d1c250a-e61b-44d9-88ed-5944d1962f5e"  # Claude Code's public id
OAUTH_TOKEN_URL = "https://platform.claude.com/v1/oauth/token"
OAUTH_USAGE_URL = "https://api.anthropic.com/api/oauth/usage"
OAUTH_BETA = "oauth-2025-04-20"
_usage_cache = {}                  # account name -> {"pct": float, "ts": float}
_route_state = {"name": None}


def _keychain_service(config_dir):
    """Claude Code's own Keychain item derivation (macOS)."""
    if not config_dir:
        return "Claude Code-credentials"
    import hashlib, unicodedata
    nfc = unicodedata.normalize("NFC", config_dir)
    return "Claude Code-credentials-" + hashlib.sha256(nfc.encode()).hexdigest()[:8]


def _read_creds(config_dir):
    try:
        r = subprocess.run(["security", "find-generic-password",
                            "-s", _keychain_service(config_dir),
                            "-a", os.environ.get("USER", ""), "-w"],
                           capture_output=True, text=True, timeout=10)
        if r.returncode == 0 and r.stdout.strip():
            return json.loads(r.stdout.strip())
    except Exception:
        pass
    path = os.path.join(config_dir or os.path.expanduser("~/.claude"),
                        ".credentials.json")
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def _usage_pct(config_dir):
    """% used of the most-constrained window for one login, or None."""
    import urllib.request, urllib.error
    oauth = (_read_creds(config_dir) or {}).get("claudeAiOauth") or {}
    access, refresh = oauth.get("accessToken"), oauth.get("refreshToken")
    if not access:
        return None

    def call(tok):
        req = urllib.request.Request(OAUTH_USAGE_URL, headers={
            "Authorization": f"Bearer {tok}", "anthropic-beta": OAUTH_BETA})
        try:
            with urllib.request.urlopen(req, timeout=10) as r:
                return r.status, json.loads(r.read().decode())
        except urllib.error.HTTPError as e:
            return e.code, None
        except Exception:
            return None, None

    code, usage = call(access)
    if code == 401 and refresh:
        req = urllib.request.Request(
            OAUTH_TOKEN_URL, method="POST",
            headers={"Content-Type": "application/json"},
            data=json.dumps({"grant_type": "refresh_token",
                             "refresh_token": refresh,
                             "client_id": OAUTH_CLIENT_ID}).encode())
        try:
            with urllib.request.urlopen(req, timeout=10) as r:
                fresh = json.loads(r.read().decode()).get("access_token")
        except Exception:
            fresh = None
        if fresh:
            code, usage = call(fresh)
    if code != 200 or not isinstance(usage, dict):
        return None
    worst = None
    for key in ("five_hour", "seven_day", "seven_day_opus", "seven_day_sonnet"):
        w = usage.get(key)
        u = w.get("utilization") if isinstance(w, dict) else w
        if isinstance(u, (int, float)):
            worst = u if worst is None else max(worst, u)
    return worst


def _route_subscription(env):
    """Point the child at the plan with the most headroom (see block comment)."""
    if not ROUTER_ON or os.environ.get("CLAUDE_CONFIG_DIR"):
        return                                   # off, or operator pinned a dir
    candidates = [("default", "")]
    try:
        candidates += sorted(
            (d.name, os.path.join(ACCOUNTS_DIR, d.name))
            for d in os.scandir(ACCOUNTS_DIR) if d.is_dir())
    except OSError:
        pass
    if len(candidates) < 2:
        return                                   # nothing to route between
    import time as _t
    now = _t.time()
    best_name, best_cfg, best_pct = None, None, None
    for name, cfg in candidates:
        c = _usage_cache.get(name)
        if not c or now - c["ts"] > ROUTER_TTL:
            pct = _usage_pct(cfg)
            if pct is None:
                _usage_cache.pop(name, None)
                continue                         # not signed in / endpoint down
            c = {"pct": pct, "ts": now}
            _usage_cache[name] = c
        if best_pct is None or c["pct"] < best_pct:
            best_name, best_cfg, best_pct = name, cfg, c["pct"]
    if best_name is None:
        return
    if best_cfg:
        # share the transcript store so sessions resume under any plan
        src = os.path.expanduser("~/.claude/projects")
        dst = os.path.join(best_cfg, "projects")
        try:
            os.makedirs(src, exist_ok=True)
            if not os.path.lexists(dst):
                os.symlink(src, dst)
        except OSError:
            pass
        env["CLAUDE_CONFIG_DIR"] = best_cfg
    else:
        env.pop("CLAUDE_CONFIG_DIR", None)
    if best_name != _route_state["name"]:
        _route_state["name"] = best_name
        print(f"[router] turns run on plan {best_name!r} ({best_pct:.0f}% used)",
              file=sys.stderr, flush=True)


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


_META_KEYS = ("session_id", "num_turns", "duration_ms")


def _parse_json_result(raw):
    """claude --output-format json → (reply_text, meta) where meta may carry
    session_id / num_turns / duration_ms."""
    try:
        d = json.loads(raw)
    except (ValueError, TypeError):
        return raw, {}
    if not isinstance(d, dict):
        return raw, {}
    meta = {k: d[k] for k in _META_KEYS if d.get(k) is not None}
    return (d.get("result") or "").strip(), meta


def forget(key):
    """Clear one conversation's memory. Returns True if anything was removed."""
    try:
        os.remove(_memory_path(key))
        return True
    except OSError:
        return False


def current_session(key):
    """The claude session id stored for a conversation key (or None) — read without
    running a turn. For callers that need to publish/inspect the live session id."""
    return _read_session(_memory_path(key)) if key else None


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
    auto_memory=True,
):
    """Run one agent turn.

    `append_system_prompt` — channel policy from the adapter (engine has none).
    `remember` — conversation key (or path); when set, the engine loads that
        conversation's stored session id, `--resume`s it, and saves the new id back,
        so successive turns with the same key remember each other. Omit for a
        stateless one-shot. `session_id` (if passed) overrides the stored id.
    `auto_memory` — Claude Code's own per-project auto-memory (durable facts under
        ~/.claude/projects/<cwd>/memory/, loaded by EVERY session in that cwd — it
        crosses conversation keys and stateless runs). False disables it for this
        turn: the fully-clean option for cron one-shots, or for per-user keys that
        must not see each other's facts.
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
        et = event.get("type")
        if et == "system" and event.get("subtype") == "init":
            if event.get("session_id"):
                meta["session_id"] = event["session_id"]
        elif et == "result":
            for k in _META_KEYS:
                if event.get(k) is not None:
                    meta[k] = event[k]

    env = _child_env(auto_memory)

    if stream:
        final = _run_streaming(
            cmd, text, workdir, on_event, _track_session,
            input_via=input_via, proc_holder=proc_holder, env=env,
        )
    else:
        raw = _run_blocking(
            cmd, text, workdir, input_via=input_via, timeout=timeout, env=env,
        )
        if capture_blocking:
            final, m = _parse_json_result(raw)
            meta.update(m)
        else:
            final = raw

    if mem_path and meta.get("session_id"):
        _write_session(mem_path, meta["session_id"])

    if return_meta:
        return {"text": final, **{k: meta.get(k) for k in _META_KEYS}}
    return final


def _run_blocking(cmd, text, cwd, input_via="argv", timeout=None, env=None):
    env = env if env is not None else _child_env()
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
                   proc_holder=None, env=None):
    env = env if env is not None else _child_env()
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
