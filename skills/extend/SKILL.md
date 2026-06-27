---
name: extend
description: >-
  Extend claude-p-agent — add tools, adapters (Telegram, web, voice), channel
  prompts, and self-improvement. Use when the user wants a new interface, tool,
  integration, or to grow what the agent can do.
---

# Extend claude-p-agent

This repo ships **only** a terminal TUI (`./tui.sh`) and a tiny engine (`agent.py`).
Everything else is yours to add. The engine does not know about Telegram, voice,
public channels, or trust tiers — **adapters** do.

## Mental model

```
your interface  →  adapter script  →  run_turn(text, append_system_prompt=..., ...)
                                              ↓
                                        claude -p @ AGENT_DIR
                                              ↓
                                   CLAUDE.md + tools/ + skills/
```

- **Persona** = `CLAUDE.md` in the agent directory (gitignored; copy from `CLAUDE.md.example`).
- **Tools** = executable scripts in `tools/` the agent runs via Bash.
- **Adapter** = thin Python (or any language) that calls `run_turn()` and maps an input source to text.
- **Channel policy** = extra system prompt + optional CLI flags passed by the adapter, not baked into `agent.py`.

Import the engine from another repo:

```bash
export CLAUDE_P_AGENT_HOME=/path/to/claude-p-agent
```

```python
import os, sys
sys.path.insert(0, os.environ["CLAUDE_P_AGENT_HOME"])
from agent import read_prompt, run_turn

reply = run_turn(
    user_text,
    append_system_prompt=read_prompt("adapters/prompts/public.md"),  # you create this
    extra_args=["--permission-mode", "plan"],  # optional lock for untrusted channels
    on_event=callback,  # optional — enables stream-json in the TUI pattern
)
```

## Add a tool

1. Drop an executable script in `tools/` (or gitignored `tools/local/` for private stuff).
2. Shape: `toolname <verb> [args…]` → plain text on stdout; exit non-zero on misuse.
3. Describe it in `CLAUDE.md` under "your tools" — that description is the only registration.
4. Secrets go in `.env`, read from the environment inside the script.

Run `tools/verify` after code changes before claiming something works.

## Add an adapter (Telegram, web, cron, …)

1. Create `adapters/yours.py` (or a separate repo that imports `CLAUDE_P_AGENT_HOME`).
2. Receive messages from your transport (HTTP, WS, Telegram long-poll, etc.).
3. Call `run_turn()` per message. For untrusted channels, pass:
   - `append_system_prompt` — a markdown file you own describing what strangers may ask
   - `extra_args` — e.g. `--permission-mode plan --disallowedTools Write Edit Bash`
4. Optional launcher: `your-thing.sh` that `exec python3 adapters/yours.py` (same pattern as `tui.sh`).

**Do not** add channel logic to `agent.py`. Keep the engine dumb.

## Add a "build" tool (self-improvement)

The agent can grow itself by spawning **separate** Claude Code sessions to write code:

```python
# tools/build — sketch; implement to taste
subprocess.run(
    ["claude", "--print", task, "--dangerously-skip-permissions"],
    cwd=target_dir,
    env=scrubbed_env(),  # same scrub as agent.py — or import scrubbed_env
)
```

Point `build run . "add a telegram adapter"` at the agent's own directory and it adds files under `adapters/`, `tools/`, etc. Keep destructive self-modification on **trusted** adapters only (your keyboard TUI, not a public webhook).

## Reference implementations (separate repos)

These are **not** bundled. Clone and wire them when you want that surface:

| Surface | Repo | Notes |
|---|---|---|
| Voice + avatar + TTS | [clawd-video-chat](https://github.com/clawdbotatg/clawd-video-chat) | `cc-bridge.py` calls `run_turn`; prompts in that repo |
| Multi-session coding UI | [clawd-harness](https://github.com/clawdbotatg/clawd-harness) | Interactive PTY sessions; not `claude -p` |

## Checklist after extending

- [ ] `tools/verify` passes
- [ ] New secrets in `.env.example` (names only, no values)
- [ ] Channel prompts live with the adapter that uses them
- [ ] Untrusted channels get CLI locks via `extra_args`, not persona wishful thinking
