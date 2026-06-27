# claude-p-agent

> **An agent is `claude -p` in a directory, with a persona and tools.**

No framework. No orchestration loop. **Claude Code is the loop.** This repo ships:

- **`agent.py`** — spawn `claude -p`, scrub env, stream optional events
- **`./tui.sh`** — talk to your agent in a terminal
- **`skills/extend/`** — how to add tools, adapters, and interfaces

That's it. Telegram, web UI, voice, cron — **you add them** (or ask your agent to build them). See **[skills/extend/SKILL.md](skills/extend/SKILL.md)**.

Optional related projects (not bundled):

- [clawd-video-chat](https://github.com/clawdbotatg/clawd-video-chat) — voice / avatar / TTS
- [clawd-harness](https://github.com/clawdbotatg/clawd-harness) — multi-session coding UI

## Quickstart

You need the [`claude` CLI](https://docs.claude.com/en/docs/claude-code) on a Claude subscription (OAuth, not an API key).

```bash
git clone https://github.com/clawdbotatg/claude-p-agent && cd claude-p-agent
cp CLAUDE.md.example CLAUDE.md   # edit — this is your agent
cp .env.example .env             # optional
./tui.sh
```

First thing to try: *"Read skills/extend/SKILL.md and add a tool I ask for."*

## The engine

```python
from agent import run_turn

run_turn(
    "hello",
    append_system_prompt=...,   # optional — from YOUR adapter
    session_id=...,             # optional — --resume
    extra_args=...,           # optional — CLI flags from YOUR adapter
    on_event=...,             # optional — stream-json (TUI uses this)
)
```

**Persona** = `CLAUDE.md` in `AGENT_DIR` (default: repo root).

External adapters import the engine:

```bash
export CLAUDE_P_AGENT_HOME=/path/to/claude-p-agent
```

## What's in the repo

| Piece | What it is |
|---|---|
| **`agent.py`** | spawn `claude -p`, scrub env, return reply |
| **`tui.sh` / `adapters/cli.py`** | terminal REPL |
| **`CLAUDE.md.example`** | persona template (real `CLAUDE.md` is gitignored) |
| **`tools/verify`** | compile + test before you say "done" |
| **`tools/local/`** | gitignored slot for your private tools |
| **`skills/extend/`** | how to grow the agent |

## Make it yours

1. **Persona** → edit `CLAUDE.md`
2. **Tools** → drop scripts in `tools/` or `tools/local/`
3. **New interface** → build an adapter (see `skills/extend/SKILL.md`) or point your agent at that skill
4. **Secrets** → `.env`

## License

MIT. Wrapper around the `claude` CLI; bring your own Claude Code subscription.
