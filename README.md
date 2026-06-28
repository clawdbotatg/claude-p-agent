# claude-p-agent

> **An agent is `claude -p` in a directory, with a persona and tools.**

No framework. No orchestration loop. **Claude Code is the loop.** This repo ships:

- **`agent.py`** — spawn `claude -p`, scrub env, stream optional events
- **`./tui.sh`** — talk to your agent in a terminal
- **`skills/extend/`** — how to add tools, adapters, and interfaces

That's it. Telegram, web UI, voice, cron — **you add them** (or ask your agent to build them). See **[skills/extend/SKILL.md](skills/extend/SKILL.md)**.

**Typical path:** clone this repo as your **brain** (persona + tools), then wire **[clawd-video-chat](https://github.com/clawdbotatg/clawd-video-chat)** (or another adapter) with `CLAUDE_P_AGENT_HOME` + `CC_BRIDGE_CWD` pointing here. `./tui.sh` is the dev/bootstrap console — not how most people talk to the agent day-to-day.

Optional related projects (not bundled):

- [clawd-video-chat](https://github.com/clawdbotatg/clawd-video-chat) — voice / avatar / TTS
- [clawd-harness](https://github.com/clawdbotatg/clawd-harness) — multi-session coding UI

## Quickstart

You need the [`claude` CLI](https://docs.claude.com/en/docs/claude-code) on a Claude subscription (OAuth, not an API key).

```bash
git clone https://github.com/clawdbotatg/claude-p-agent && cd claude-p-agent
./tui.sh    # first run asks what to call your agent and writes CLAUDE.md
```

Optional: `cp .env.example .env` for `BRAIN_DIRS` and other knobs.

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

## Memory

The engine is **stateless** — a turn is a pure function. **Memory is the adapter's
job**, on purpose: only the adapter knows the conversation's scope (one session?
per-user? per-channel? when to reset?), and the same engine also serves stateless
one-shots (cron jobs that must start fresh each run). So `run_turn` takes a
`session_id` rather than owning one.

The canonical, dead-simple wiring is **`--remember <file>`** (in both `cli.py` and
`adapters/run.py`):

```bash
echo "remember: my number is 42" | ./tui.sh --remember ~/.cache/myagent.session
echo "what's my number?"         | ./tui.sh --remember ~/.cache/myagent.session   # → 42

# general runner — own cwd/persona/tools, what external projects (Node/cron) call:
python3 adapters/run.py "<prompt>" --cwd /my/project --remember /my/project/state/session.txt \
  --tool Read --tool "Bash(node x.js:*)" --max-turns 15
```

It reads a saved claude session id, `--resume`s it, and writes the new id back — so
successive turns remember each other. **Delete the file (or `/new` in the TUI) to clear
it.** Omit `--remember` for stateless one-shots. Under the hood it just threads
`session_id` through `run_turn`: wire it once per adapter, get memory.

## What's in the repo

| Piece | What it is |
|---|---|
| **`agent.py`** | spawn `claude -p`, scrub env, return reply |
| **`tui.sh` / `adapters/cli.py`** | terminal REPL (`--remember <file>` for persistent memory) |
| **`adapters/run.py`** | general non-interactive runner — own `--cwd`/`--tool`/`--remember`, for shell/Node/cron callers |
| **`CLAUDE.md.example`** | persona template (real `CLAUDE.md` is gitignored) |
| **`tools/verify`** | compile + test before you say "done" |
| **`tools/local/`** | gitignored slot for your private tools |
| **`skills/extend/`** | how to grow the agent |

## Make it yours

1. **Persona** → `./tui.sh` creates `CLAUDE.md` on first run; edit anytime
2. **Tools** → drop scripts in `tools/` or `tools/local/`
3. **New interface** → build an adapter (see `skills/extend/SKILL.md`) or point your agent at that skill
4. **Secrets** → `.env`

## License

MIT. Wrapper around the `claude` CLI; bring your own Claude Code subscription.
