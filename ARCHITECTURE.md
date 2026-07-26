# Architecture

Written for the agent as much as for humans: this is the map of your own
body. **Know yourself by reading, not remembering** — when in doubt,
`tools/self` (status/drift — what my body is, from disk), `tools/vitals`
(what my mind is running on *this turn*: model, context fullness,
subscription + plan usage, engine — read live from my own transcript and
the router cache), `git log`, and the files themselves are the truth; this
document is the guide to where truth lives.

Two pieces in this repo. Everything else is a module.

## The engine

`agent.py` spawns `claude -p` in `AGENT_DIR` with the env scrubbed so the
child runs on your subscription (not metered API). It owns memory keys
(`remember=<key>` → session ids resumed/saved, adapters never touch them)
and honors exactly **two module extension points** on the spawn path:

1. **env hook** — every executable `modules/<name>/env` runs before every
   spawn; `KEY=VAL` stdout lines merge into the child env (`KEY=` removes).
   Failures are ignored; stderr passes through. The subscription router is
   this: `modules/router/env`.
2. **settings merge** — `hooks.base.json` (repo root, tracked — the guard
   hook lives there), then every `modules/<name>/hooks.json`, merge into
   generated files (`.hooks.generated.json`, `.mcp.generated.json`,
   gitignored) passed via `--settings` / `--mcp-config`. Declarations may
   contain Claude Code hooks (UserPromptSubmit / PreToolUse / PostToolUse /
   Stop …) and `mcpServers` (stateful tool servers). `$MODULE_DIR` /
   `$AGENT_HOME` are replaced with absolute paths at merge time.

**The engine never imports module code.** A broken module costs one
capability; the mind always spawns. Engine changes are ring 0 — see
`skills/self`.

**Alternate engines** (contract: `PLAN-ENGINES.md`): claude is the built-in
engine; a module may ship an executable `modules/<name>/engine` speaking
protocol v0 (one JSON request on stdin, JSONL events on stdout, last line
`{"type":"result","text","state"}`). The kernel keeps the memory *keys*;
the engine defines the *state blob* under them, namespaced per engine
(`.memory/<key>@<engine>.state`). Installing an engine never activates it —
selection is explicit (`ENGINE=<name>` in `.env`, or `run_turn(engine=…)`),
and claude-only options (`extra_args`, `session_id`) hard-error on external
engines rather than silently dropping. This is a deliberate third seam, not
a drift from the two-extension-point rule: an engine replaces the spawn
target; it doesn't hook into claude's spawn.

```python
from agent import run_turn

run_turn(
    "hello",
    append_system_prompt=...,  # optional — channel policy from an adapter
    remember="some-key",       # optional — engine-owned conversation memory
    extra_args=...,            # optional — CLI locks for untrusted channels
    on_event=...,              # optional — stream-json
)
```

**TUI:** `adapters/cli.py` → `run_turn()` with streaming renderer, launched
via `./tui.sh` — the bootstrap/debug console, and the one interface that
must always work.

**Persona:** `CLAUDE.md` in the agent directory (Claude Code loads it
automatically; gitignored — copy `CLAUDE.md.example` or let `./tui.sh`
bootstrap it).

## Modules

A module is a **git repo cloned into `modules/<name>/`** (gitignored). The
brain repo commits only **`modules.lock`** — `name  url  @ sha` — so one
install/update/removal is one lock commit, and `tools/module sync` rebuilds
the whole body from the lock (the resurrection path). A module's `MODULE.md`
is its manifest: what it is, what it needs, wiring, verification, **what can
go wrong**, uninstall.

What a module can ship: `tools/` scripts, `skills/`, a long-running adapter
process that imports the engine, an `env` hook, a `hooks.json`. Dependencies
live inside the module's folder — stdlib-only protects the engine, never
modules.

- Mechanics: `tools/module list|add|remove|update|sync|scaffold|publish`
- Judgment (find → audit → checkpoint → wire → verify → lock commit):
  `skills/module` — the agent is the package manager
- Registry: GitHub topic **`claude-p-agent-module`**; publishing is pushing
  a repo with that topic
- Trust: reading the code is the floor; the `attest` module adds EAS
  attestations on the exact pinned SHA (checked at install, offered back
  to the human after a module proves itself in use — "Closing the loop"
  in `skills/module`). Local trust list, no global scores.

## Self-protection (summary — the law is `skills/self`)

- Rings of ceremony; ring 0 rehearses in a clone; never experiment in the
  live body (the working tree IS the running agent).
- `tools/verify` (compile + tests + **doc-drift**: docs that lie about the
  code fail) → `tools/smoke` (one live turn) → `tools/checkpoint [label]`
  (moves `known-good`, plants named `checkpoint/<date>-<label>` tags, backs
  up the persona outside the repo) → `tools/watchdog` (dumb cron shell,
  no AI, resets tracked files to `known-good`).
- The **guard hook** (`hooks.base.json` → `tools/guard-check`) mechanically
  blocks self-edits to the recovery system without a human's
  `touch .guard-ok`.
- `tools/self` — status (ground truth from disk) and drift (the doc checker).

## Layout

| Path | What |
|---|---|
| `agent.py` | the engine (ring 0) |
| `tui.sh`, `adapters/cli.py` | terminal REPL (ring 0) |
| `adapters/run.py` | non-interactive runner for shell/cron callers |
| `modules/` (gitignored) + `modules.lock` (tracked) | the module system |
| `tools/` | module, self, verify, smoke, checkpoint, watchdog, guard-check |
| `tools/local/` (gitignored) | private tool overlay |
| `skills/` | self, module, extend |
| `hooks.base.json` | always-on hook declarations (the guard) |
| `.memory/` (gitignored) | engine-owned conversation session ids |

## Env vars

| Var | Meaning |
|---|---|
| `AGENT_DIR` | cwd for `claude -p` (persona + tools home) |
| `CLAUDE_P_AGENT_HOME` | path to import `agent.py` from another repo |
| `CLAUDE_P_MODULES` | override the modules dir (default `AGENT_DIR/modules`) |
| `CLAUDE_P_ENV_HOOK_TIMEOUT` | per-module env hook budget, seconds (default 60) |
| `BRAIN_DIRS` | extra readable dirs (`:`-separated → `--add-dir`) |
| `CLAUDE_ARGS` | extra CLI flags on every turn |
| `CLAUDE_BIN` | path to claude CLI (default: `claude`) |
| `ENGINE` | default engine for every turn (default `claude` = built-in; a name selects `modules/<name>/engine`) |
| `GH_OWNER` | owner for published modules / bare-name resolution |

Adapter-specific vars (bot tokens, etc.) belong in the module that uses
them, documented in **its** MODULE.md, values in the gitignored `.env`.

## Related repos (not modules, not bundled)

| Surface | Repo |
|---|---|
| Voice / avatar / TTS | [clawd-video-chat](https://github.com/clawdbotatg/clawd-video-chat) |
| Multi-session coding UI | [clawd-harness](https://github.com/clawdbotatg/clawd-harness) |
