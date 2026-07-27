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

**Bring any brain — Claude Code is the default, not a dependency.** The
[`claude` CLI](https://docs.claude.com/en/docs/claude-code) on a Claude
subscription is the only *full body* (tools, self-editing, module
installs). Without it, `./setup` bootstraps onto a **local Ollama** model
(free, private, no account — it recommends the smallest one measured to
actually work) or **any OpenAI-style API key** (OpenRouter, Groq, …) —
chat-only engines, still your agent. Setup detects what's on the machine,
offers to install what's missing, and walks you through sign-in.

```bash
git clone https://github.com/clawdbotatg/claude-p-agent && cd claude-p-agent
./setup             # one typed question (a name) — then the agent takes over
```

`setup` writes a persona and wakes the agent for its **first
conversation**: it asks how you want it to work — engine, modules,
channels — in plain language, and installs what you ask for itself
(audited and verified, per `skills/module`). No menus. Saying "nothing"
is a great answer: **you start with zero modules** — the lightest,
fully-auditable agent, just this repo plus the `claude` CLI (`agent.py`
is the entire engine, one file). Later: `./tui.sh --remember main`
reopens that same thread; plain `./tui.sh` is a throwaway one;
`tools/module sync` installs the full pinned loadout from `modules.lock`.

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

**Engines are swappable.** Claude Code is the built-in default; an *engine
module* — its own repo, pinned + attestable like any module, shipping one
executable that speaks a small JSON protocol — can run turns instead:
`run_turn(..., engine="engine-oai")`, `ENGINE=<name>` in `.env`, or
`adapters/run.py --engine <name>`. First one:
[claude-p-engine-oai](https://github.com/clawdbotatg/claude-p-engine-oai) —
any OpenAI-style `/chat/completions` route (Bankr, OpenRouter) as a chat
brain. Contract: [`PLAN-ENGINES.md`](PLAN-ENGINES.md); prove a new engine
with `tools/engine-check <name>`. Installing never activates; chat engines
have no tools; self-modification stays on the claude engine.

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
- **A second memory layer lives underneath**: Claude Code's own **auto-memory**
  saves durable user facts to `~/.claude/projects/<cwd>/memory/` and loads them
  into *every* session in that cwd — across keys and even "stateless" runs. So
  `remember: my number is 42` above can come back on a *fresh* key too (as a
  saved user fact, not a session). For a single-owner agent brain that's a
  feature. When it isn't — cron jobs that must start truly clean, or per-user
  keys that must not see each other's facts — pass `auto_memory=False`
  (`--no-auto-memory` on `run.py`) to turn it off for that turn.
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
| **`setup`** | the one command after cloning — writes a persona, then the agent itself asks how you want it to work (default: zero modules) |
| **`agent.py`** | spawn `claude -p`, scrub env, return reply — plus the two module extension points |
| **`tui.sh` / `adapters/cli.py`** | terminal REPL (`--remember <key>` to pick a conversation) |
| **`adapters/run.py`** | general non-interactive runner — own `--cwd`/`--tool`/`--remember <key>`, for shell/Node/cron callers |
| **`CLAUDE.md.example`** | persona template (real `CLAUDE.md` is gitignored) |
| **`modules.lock`** | the agent's installed modules, pinned by commit (`tools/module sync` rebuilds them) |
| **`tools/module`** | list/add/remove/update/sync/scaffold/publish modules |
| **`tools/self`** | status (what am I right now, from disk) + doc-drift check |
| **`tools/vitals`** | runtime vitals (what am I running as, this turn): model, context fullness, subscription + plan usage, engine |
| **`tools/verify`** | compile + tests + doc-drift before you say "done" |
| **`tools/smoke`** | one live turn, exit code — is the agent alive? |
| **`tools/checkpoint`** | certify a green HEAD as `known-good` (+ named `checkpoint/…` tags) + back up the persona |
| **`tools/watchdog`** | dumb cron healer — resets to `known-good` when verify keeps failing |
| **`tools/guard-check`** | hook that stops the agent editing its own recovery system |
| **`tools/local/`** | gitignored slot for your private tools |
| **`skills/module/`** | the agent as package manager — install, build, publish modules |
| **`skills/extend/`** | how to grow the agent |
| **`skills/self/`** | how the agent changes itself without breaking itself |

## Modules

**A capability is a module: a git repo cloned into `modules/<name>/`, pinned
in `modules.lock`, described by its `MODULE.md`.** The agent itself installs,
audits, wires, and verifies them (see `skills/module`) — there is no loader
and no plugin API; the engine only honors an `env` hook and a `hooks.json`
per module. Find published modules by GitHub topic
[`claude-p-agent-module`](https://github.com/topics/claude-p-agent-module);
publish yours with `tools/module publish`. First one:
[claude-p-router](https://github.com/clawdbotatg/claude-p-router) routes
every turn to the subscription login with the most headroom.

**Trust is a loop, not a gate.** Before wiring a module the agent reads
all of its code (always), and — via the
[attest](https://github.com/clawdbotatg/claude-p-attest) module — checks
[EAS](https://attest.org) attestations on Base for the exact pinned SHA
against your local trust list. After a module has served you well, close
the loop: publish an attestation saying you ran it and didn't get rugged
(one wallet signature, pennies of gas — the agent offers the pre-filled
link; see "Closing the loop" in `skills/module`). Got rugged instead?
Attest `safe: false` with notes. That used-it-and-signed signal is what
the next agent's audit gets to lean on.

## Make it yours

1. **Persona** → `./tui.sh` creates `CLAUDE.md` on first run; edit anytime
2. **Tools** → drop scripts in `tools/` or `tools/local/`
3. **New interface** → build an adapter (see `skills/extend/SKILL.md`) or point your agent at that skill
4. **Secrets** → `.env`

## License

MIT. Wrapper around the `claude` CLI; bring your own Claude Code subscription.
