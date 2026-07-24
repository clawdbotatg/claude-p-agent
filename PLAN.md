# Plan: minimal core, modular everything

> Working name TBD (candidates: goober, tater, skosh, hitode, fugue). Below, "the agent."

**North star, one line:** the engine only spawns; everything else is a folder
convention interpreted by the agent, not a loader; git is the agent's memory,
identity, and undo button.

## 1. Shrink the core

- Extract the subscription router out of `agent.py` into `modules/router/` —
  it becomes the first real module and proves the contract.
- `agent.py` ends at: spawn `claude -p`, scrub env, memory keys, plus the two
  hook merges below. Stdlib-only, no imports from anywhere else in the repo.
- Exactly **two** extension points in the engine, both dumb and declarative:
  1. **env hook** — any executable `modules/*/env` runs before spawn; its
     `KEY=VAL` stdout merges into the child env; failures ignored (~10 lines).
  2. **hooks merge** — `modules/*/hooks.json` (Claude Code native hooks:
     UserPromptSubmit / PreToolUse / PostToolUse / Stop) merged into one
     generated settings file passed via `--settings` (~20 lines).
- The engine **never imports module code**. A broken module loses one
  capability; the mind always spawns.

## 2. The module contract

- A module = a git repo cloned into `modules/<name>/`. That folder is
  **gitignored**; the brain repo commits **`modules.lock`** instead:
  `name  url  @ pinned-SHA`. One install/update/removal = one lock commit.
- **`MODULE.md`** is manifest and docs in one (prose — the installer is an
  LLM). Required sections: what it is · what it needs (env vars, deps,
  long-running process?) · wiring steps · how to verify · **what can go
  wrong** · how to uninstall.
- Four attachment points, all folder-shaped: `tools/` (Bash scripts),
  `skills/` (knowledge + taste), adapter processes (call `run_turn()`),
  and the env/hooks declarations above.
- Modules keep their own deps inside their folder (venv, node_modules).
  The stdlib-only rule protects the engine, never constrains modules.
- `tools/module add|remove|update|list|scaffold` — thin helpers; the
  *agent* does the judgment parts (audit, wiring, verify).

## 3. Self-knowledge — make the operations native

The agent wakes up amnesiac every turn; it knows itself by reading. So the
docs ARE the capability:

- **`ARCHITECTURE.md`** rewritten agent-first: the module contract, the
  attachment map, "read, don't remember."
- **`skills/self`** gains: `modules/` as ring 2 with *per-module* rollback;
  one-change-one-commit with messages written as letters to the next self
  ("if X breaks, suspect this commit").
- **`skills/module`** (new): the install flow — find → **audit the code** →
  `checkpoint` first → wire → verify with a harmless live demo → commit the
  lock — and the author/publish flow for building new ones.
- **Version navigation as a first-class skill:**
  - Named checkpoints: `checkpoint/<date>-<label>` tags, not just one
    `known-good`.
  - Rollback is a conversation: the agent narrates what a reset discards
    and offers to re-apply what should survive.
  - "When did this break?" → `git bisect run tools/verify`.
  - Module rollback = revert one lock commit + checkout old SHA in the
    module's own repo. Brain history untouched.
- Recovery ladder unchanged (each layer assumes the one above is dead):
  `git revert` → `tools/smoke` → `tools/watchdog` resets to `known-good`
  (dumb shell, no AI) → resurrect anywhere from brain repo + `modules.lock`
  + the external persona backup.

## 4. The registry

- **Publishing = pushing a GitHub repo with a topic tag** (`<name>-module`).
  **Discovery = `gh search repos --topic`.** No infrastructure, ever.
- "I want Telegram" → agent searches the topic → found: clone, audit,
  install per skills/module → not found: `scaffold`, build it, verify it,
  then **offer to publish** so the next person hits the found path.
- Ship **three exemplar modules**, one per attachment pattern, as the
  culture-setting templates people copy:
  1. `router` — spawn-time env (extracted in step 1)
  2. `cron` — scheduled; wraps OS cron/launchd, never reinvents it;
     jobs are stateless `adapters/run.py` one-shots; includes the
     "review my own job logs daily" self-monitoring entry
  3. `telegram` — long-running adapter; per-chat memory via
     `remember="tg-<chat_id>"`; allowlist + CLI locks for strangers;
     declares its process-supervision needs in MODULE.md

## 5. Prove it (acceptance = conversations, not tests)

- "add telegram" → working bot, one lock commit, live round-trip shown.
- "roll back to before the memory module" → narrated, clean, done.
- "what changed this week and why?" → answered from git log alone.
- "update the cron module" → pulled, verified, SHA bumped, one commit.
- **Resurrection drill:** clone the brain repo on a fresh machine + restore
  the backup dir → agent rebuilds itself (modules re-cloned at pinned SHAs,
  wiring re-run) and passes `tools/smoke`.

## Order of work

1. Router extraction + the two engine hooks (proves the contract in one move)
2. `modules.lock` + `tools/module` + `MODULE.md` format
3. `skills/module` + `skills/self` + `ARCHITECTURE.md` rewrites
4. cron + telegram exemplars, topic tag, publish flow
5. The five acceptance conversations, then the resurrection drill
