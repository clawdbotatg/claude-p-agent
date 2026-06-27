# Architecture

Three layers. One engine.

## claude-p-agent (this repo)

**The engine.** `agent.py` spawns `claude -p` in `AGENT_DIR` with env scrubbed so the
child runs on your subscription.

```python
from agent import run_turn

run_turn(
    "hello",
    append_system_prompt=...,  # optional — from the adapter, not the engine
    session_id=...,            # optional — --resume
    extra_args=...,            # optional — CLI flags from the adapter
    on_event=...,              # optional — stream-json
)
```

**Persona** = `CLAUDE.md` in the agent directory (Claude Code loads it automatically).

**The engine does not know** about public/private, voice, backchannel, or Telegram.
Adapters own channel policy and pass `append_system_prompt` + `extra_args`.

**One-off agents** = clone this repo, edit `CLAUDE.md` + `tools/`, wire an adapter.

Import from other repos:

```bash
export CLAUDE_P_AGENT_HOME=/path/to/claude-p-agent
```

## Adapters (thin)

Map an input source → `run_turn(...)`.

| Adapter | Repo | Owns |
|---|---|---|
| `adapters/cli.py` | claude-p-agent | `adapters/prompts/` for `--public` sim |
| `adapters/telegram.py` | claude-p-agent | owner vs stranger prompts + `CLAUDE_ARGS_PUBLIC` |
| `cc-bridge.py` | clawd-video-chat | `prompts/voice*.md`, `[SAY]` TTS, WS gateway |
| `controller/agent.py` | clawd-harness | `controller/prompts/` + MCP fleet tools |

## clawd-harness (workhorse)

**Not an agent.** Interactive `claude` sessions in PTYs over WebSocket (`server.py`).

The brain's `tools/code` helper drives harness sessions to do real coding. The
harness never imports `agent.py`.

## clawd-video-chat (face)

Wake word, avatar, TTS, backchannel. Calls `run_turn` from claude-p-agent.
Channel prompts live in **`clawd-video-chat/prompts/`**, not here.

```
mic / backchannel → cc-bridge → run_turn() → claude -p @ AGENT_DIR (clawd clone)
                     ↓
                  [SAY] → TTS → room
```

## Env vars

| Var | Meaning |
|---|---|
| `AGENT_DIR` | cwd for `claude -p` (persona + tools home) |
| `CLAUDE_P_AGENT_HOME` | path to import `agent.py` from another repo |
| `CC_BRIDGE_CWD` | brain directory for video (usually same as agent clone) |
| `CLAUDE_ARGS` | extra CLI flags on every turn (engine default) |
| `CLAUDE_ARGS_PUBLIC` | used by **telegram/cli adapters**, not the engine |
