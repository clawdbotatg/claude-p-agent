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

**One system, everywhere: a conversation has a *key*, and the agent remembers it.**
That's the whole model. The only thing any adapter decides is *what its key is* —
a chat id, a thread name, a user id, anything stable.

```bash
# Python (in-process callers — PM, TUI, your own adapter):
run_turn("remember: my number is 42", remember="alice")
run_turn("what's my number?",          remember="alice")   # → 42

# CLI (shell / Node / cron — anything that shells out):
python3 adapters/run.py "<prompt>" --cwd /my/project --remember alice \
  --tool Read --tool "Bash(node x.js:*)" --max-turns 15
python3 adapters/run.py --forget alice          # reset that conversation
```

- **Same key → continues. New key → fresh. No `remember` → stateless one-shot**
  (what cron jobs want — they must start clean each run).
- The **engine owns every mechanic** — it loads the key's stored claude `session_id`,
  `--resume`s it, captures the new id (incl. the awkward blocking-turn case), and saves
  it back. Adapters never touch a `session_id`. Wire `remember=<key>` once; get memory.
- A key is a **name** (stored in the engine's `.memory/` dir) or a **path** (contains a
  `/` → you pin the location, e.g. inside your project's `state/`). Reset = `forget(key)`
  / `--forget key`, or `/new` in the TUI.
- The **TUI is ephemeral by default** — each instance is its own throwaway session
  (two TUIs at once = two separate threads; closing one and reopening starts fresh, like
  `/new`). Pass **`--remember <key>`** to make it persistent — that conversation survives
  close/reopen, and two instances with the *same* key deliberately share one thread.
  `run.py` is likewise stateless unless you pass `--remember`. You persist or share only
  when you ask to.

**This is the default — reach for it unless you have a concrete reason not to.** Need the
session id for something external (a context gauge, a dashboard)? You don't have to give up
`remember=` for that — `run_turn(..., return_meta=True)` still hands you the `session_id`
(and `current_session(key)` reads it without a turn), so publish it from there. Hand-rolling
the whole session yourself is a rare exception, not the norm. If you're unsure: `remember=<key>`.

## What's in the repo

| Piece | What it is |
|---|---|
| **`agent.py`** | spawn `claude -p`, scrub env, return reply |
| **`tui.sh` / `adapters/cli.py`** | terminal REPL (remembers by default; `--remember <key>` to pick a conversation) |
| **`adapters/run.py`** | general non-interactive runner — own `--cwd`/`--tool`/`--remember <key>`, for shell/Node/cron callers |
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
