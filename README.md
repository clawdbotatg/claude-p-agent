# claude-p-agent

> **An agent is `claude -p` in a directory, with a persona and tools — plus adapters
> that call `run_turn()`.**

No agent framework. No orchestration loop. **Claude Code is the loop.** The engine
is ~100 lines (`agent.py`). Everything else is config: `CLAUDE.md`, `tools/`, and
thin adapters in other repos.

See **[ARCHITECTURE.md](ARCHITECTURE.md)** for how this fits with
[clawd-video-chat](https://github.com/clawdbotatg/clawd-video-chat) (face) and
[clawd-harness](https://github.com/clawdbotatg/clawd-harness) (workhorse).

## Quickstart

You need the [`claude` CLI](https://docs.claude.com/en/docs/claude-code) on a
Claude subscription (OAuth, not an API key).

```bash
git clone https://github.com/clawdbotatg/claude-p-agent && cd claude-p-agent
cp CLAUDE.md.example CLAUDE.md
cp .env.example .env
./tui.sh
```

Edit **`CLAUDE.md`** — that *is* the agent (gitignored). Claude Code loads it
every turn.

Self-improving example:

```bash
AGENT_DIR=examples/builder ./tui.sh
> add a tool that tells a dad joke, then use it
```

## The engine

```python
from agent import run_turn

run_turn(
    "hello",
    append_system_prompt=...,   # optional — from YOUR adapter, not the engine
    session_id=...,             # optional — --resume
    extra_args=...,             # optional — CLI flags from your adapter
    on_event=...,               # optional — stream-json
)
```

**Persona** = `CLAUDE.md` in `AGENT_DIR`.

**Channel policy** = whatever the adapter passes as `append_system_prompt`. The
engine has no built-in public/private tiers. Bundled adapters ship example prompts
in `adapters/prompts/`; video-chat owns its own in `clawd-video-chat/prompts/`.

## One agent = one clone

Twitter bot, scheduler, clawd-on-zoom — each is a **fresh clone** of this repo
with its own `CLAUDE.md` and `tools/`. Same engine, different persona.

External adapters import it:

```bash
export CLAUDE_P_AGENT_HOME=/path/to/claude-p-agent
```

## What's in the repo

| Piece | What it is |
|---|---|
| **`agent.py`** | spawn `claude -p`, scrub env, return reply |
| **`CLAUDE.md`** | persona (gitignored; `CLAUDE.md.example` is the template) |
| **`adapters/`** | hello-world front-ends (cli, telegram) + their prompt files |
| **`tools/`** | CLI scripts the agent shells out to |
| **`examples/builder/`** | self-improvement via `tools/build` |
| **`examples/prompts/`** | reference channel prompts (not loaded by the engine) |

## Adapters

An adapter maps an input source → `run_turn(...)`.

| Adapter | Where | Channel policy |
|---|---|---|
| Terminal | `adapters/cli.py` | owner keyboard; `--public` sim uses `adapters/prompts/public.md` |
| Telegram | `adapters/telegram.py` | owner DM vs stranger; `CLAUDE_ARGS_PUBLIC` tool lock |
| Voice / Zoom | `clawd-video-chat/cc-bridge.py` | `prompts/voice*.md`, backchannel, TTS |
| Fleet PM | `clawd-harness/controller/` | `controller/prompts/` + MCP fleet tools |

## Self-improvement

Point [`examples/builder/tools/build`](examples/builder/tools/build) at `.` and the
agent adds tools or edits its own `CLAUDE.md`. Keep that power on trusted adapters
only — enforce with adapter prompt + CLI flags, not engine magic.

## Make it yours

1. **Persona** → edit `CLAUDE.md`
2. **Tools** → drop scripts in `tools/` or `tools/local/` (gitignored)
3. **Front-end** → write an adapter, or use cli/telegram — see `adapters/README.md`
4. **Secrets** → `.env`

## License

MIT. Wrapper around the `claude` CLI; bring your own Claude Code subscription.
