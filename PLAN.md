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
  2. **settings merge** — `modules/*/hooks.json` (Claude Code native hooks:
     UserPromptSubmit / PreToolUse / PostToolUse / Stop) **and MCP server
     declarations** (for stateful tool servers — persistent browser, DB
     pools, vector stores) merged into one generated settings file passed
     via `--settings` (~20 lines). Same merge, both kinds of declaration.
- The engine **never imports module code**. A broken module loses one
  capability; the mind always spawns.
- **Boundary notes (audited, deliberate):** global *reply* transforms have
  no attachment point (adapters own output) — if ever truly needed, the
  answer is a third hook of the identical dumb pattern (`modules/*/reply`,
  stdin→stdout), deferred until demanded. A different loop or backend
  (Codex, custom planners) = fork the engine, keep the conventions — the
  thesis is that Claude Code *is* the loop. Module-on-module deps are prose
  in MODULE.md, resolved by the agent-as-installer, not a solver.

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

## 5. Trust layer — EAS attestations on module SHAs (later, pure add-on)

Git commit SHAs are already content addresses — `modules.lock` pins them, so
the trust layer attaches to what exists, changing nothing underneath.

- **Attestation = an EAS attestation** (Ethereum Attestation Service, on
  Base) over `{repo_url, commit_sha, module_name, verdict, notes}`, signed
  by a known key. Third-party "I audited this exact SHA and vouch" — the
  thing git author-signing can't express. (Author-signed commits are still
  required hygiene for published modules; they prove authorship, not safety.)
- **Web of trust, not global scores** — each operator keeps a trust list of
  attester keys. No staking, no reputation math, no sybil swamp. The install
  skill grows one sentence: "check attestations for the pinned SHA; for
  modules touching money/credentials, require one from the trust list."
- **Agents are auditors** — the install flow already reads the code; give
  the agent a key and it publishes its own attestation after a successful
  audit + install. Reputation emerges from usage.
- **Attestations never replace the audit.** Signed malware is an ancient
  tradition; the agent reads the code regardless.
- **Availability mirror = bgipfs** (BuidlGuidl IPFS: `npm i -g bgipfs`,
  `bgipfs upload <path>` → CID, gateway at
  `https://{CID}.ipfs.community.bgipfs.com/`, `X-API-Key` auth —
  https://www.bgipfs.com/SKILL.md). Optional, not a dependency: attesters'
  clones already satisfy the pinned SHA if GitHub drops a repo; publishing
  a module tarball to bgipfs adds a URL-stable mirror for popular modules.
  `modules.lock` may carry an optional CID column.
- Ships as **two modules** (naturally): `<name>-attest` wrapping EAS with
  `attest <repo> <sha>` / `check <repo> <sha>` + the trust list, and
  `<name>-ipfs` wrapping bgipfs for the mirror step.

**Later — CLAWD economics (designed, deferred):** bonded attestations
(stake CLAWD behind a vouch; slashable only for *intentional malice present
in the attested SHA*, never honest bugs), optimistic challenges with
commit-reveal evidence and a named council oracle (5-of-9; can rule, never
initiate), challenger bounty + burn split, module-creation bounties, and
stake-as-ranking (sort signal only — never an install gate). All of it
attaches to the same `(repo, sha)` attestations above; nothing in the
engine, lock file, or install flow changes when it arrives. Slash/challenge
events double as a broadcast immune system: agents watch flags on their own
`modules.lock` SHAs and auto-quarantine + roll back.

## 6. Prove it (acceptance = conversations, not tests)

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
6. Trust layer: the `attest` module (EAS + trust list) and the `ipfs`
   module (bgipfs mirror)
7. (later) CLAWD economics on top — bonds, challenges, bounties
