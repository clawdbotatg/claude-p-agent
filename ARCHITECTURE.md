# Architecture

Two pieces in this repo. Everything else is extension.

## claude-p-agent (this repo)

**Engine:** `agent.py` spawns `claude -p` in `AGENT_DIR` with env scrubbed so the
child runs on your subscription.

```python
from agent import run_turn

run_turn(
    "hello",
    append_system_prompt=...,  # optional — from an adapter you write
    session_id=...,            # optional — --resume
    extra_args=...,            # optional
    on_event=...,              # optional — stream-json
)
```

**TUI:** `adapters/cli.py` → `run_turn()` with streaming renderer. Launched via `./tui.sh`.

**Persona:** `CLAUDE.md` in the agent directory (Claude Code loads it automatically).

The engine does **not** know about public/private, Telegram, voice, or trust tiers.
You add those in adapters you own. See `skills/extend/SKILL.md`.

Import from other repos:

```bash
export CLAUDE_P_AGENT_HOME=/path/to/claude-p-agent
```

## Extension (not shipped here)

| You want… | Where to look |
|---|---|
| Add tools, Telegram, web, cron | `skills/extend/SKILL.md` — or ask your agent to read it and build |
| Voice / avatar / TTS | [clawd-video-chat](https://github.com/clawdbotatg/clawd-video-chat) |
| Multi-session coding UI | [clawd-harness](https://github.com/clawdbotatg/clawd-harness) |

## Env vars

| Var | Meaning |
|---|---|
| `AGENT_DIR` | cwd for `claude -p` (persona + tools home) |
| `CLAUDE_P_AGENT_HOME` | path to import `agent.py` from another repo |
| `BRAIN_DIRS` | extra readable dirs (`:`-separated → `--add-dir`) |
| `CLAUDE_ARGS` | extra CLI flags on every turn |
| `CLAUDE_BIN` | path to claude CLI (default: `claude`) |

Adapter-specific vars (Telegram tokens, etc.) belong in **your** adapter's docs, not here.
