# The Plan: minimal core, modular everything

> Working name TBD (candidates: goober, tater, skosh, hitode, fugue).
> Below, "the agent." This doc is the complete design — vision, contracts,
> safety model, roadmap — written to be read by humans *and* by the agent
> itself (it is the seed of the agent's self-knowledge).

## 0. Thesis

**An agent is `claude -p` in a directory, with a persona and tools.**
No framework. Claude Code is the loop. This plan takes that thesis to its
conclusion:

- **The engine only spawns.** Everything that can live outside the spawn
  path must.
- **Extensions are folder conventions interpreted by the agent, not a
  loader.** The framework you'd normally write is replaced by the agent's
  ability to read. The installer is an LLM: manifests are prose, audits
  are real code-reading, wiring is judgment.
- **Git is the agent's memory, identity, and undo button.** The brain repo
  + `modules.lock` on GitHub *is* the agent; any machine can resurrect it.
- **Judgment is a publishable artifact.** A module ships code *and* the
  rules for using it well (skills) as one inseparable unit — capability
  and caution install together.

### Design principles (these generated every decision below)

1. **Dumb extension points, smart interpreter.** Engine hooks are tiny,
   declarative, and failure-tolerant; all intelligence lives in the agent
   reading conventions.
2. **The engine never imports module code.** A broken module loses one
   capability; the mind always spawns.
3. **Self-protection must not depend on the self.** Last-resort recovery
   layers are deliberately dumb (shell, cron, git) because the failure
   they exist for is "the intelligence is compromised."
4. **Everything starts outside the engine.** A mechanic gets promoted into
   the engine only after proving genuinely cross-cutting *and* expressible
   in a few dumb lines (precedent: memory keys, the subscription router).
   Promotion is rare and expensive on purpose.
5. **Trust adds signal, never replaces the audit.** No signature, stake,
   or reputation score ever substitutes for the agent reading the code.

## 1. The engine

`agent.py` shrinks to its irreducible job: spawn `claude -p` in
`AGENT_DIR`, scrub the env (subscription billing, no embedded mode), own
memory keys (`remember=<key>` → engine manages session ids), and apply the
two extension points below. Stdlib-only. No imports from anywhere else in
the repo. Target: back near ~400 lines.

**First move: extract the subscription router** (currently ~145 lines of
`agent.py`) into `modules/router/` — it becomes the first real module and
proves the whole contract.

Exactly **two** extension points, both dumb and declarative:

1. **env hook** (~10 lines) — any executable `modules/*/env` runs before
   spawn; its `KEY=VAL` stdout merges into the child env; failures are
   ignored. Runs every turn, so per-turn dynamism (account routing, model
   selection via env) is covered.
2. **settings merge** (~20 lines) — `modules/*/hooks.json` is merged into
   one generated settings file passed via `--settings`. Two kinds of
   declaration ride this merge:
   - **Claude Code native hooks** — UserPromptSubmit (inject context),
     PreToolUse (gate/block tool calls), PostToolUse, Stop. This is the
     turn-time middleware layer, executed by Claude Code as subprocesses,
     never by the engine.
   - **MCP server declarations** — for stateful tool servers (persistent
     browser, DB pools, vector stores) that don't fit stateless Bash
     tools.

### Boundaries (audited, deliberate — not oversights)

- **Global reply transforms** have no attachment point (adapters own
  output). If ever truly demanded: a third hook of the identical dumb
  pattern (`modules/*/reply`, stdin→stdout). Deferred until real demand.
- **A different loop or backend** (Codex, custom planners) = fork the
  engine, keep the conventions and the `run_turn()` surface. Porting is
  cheaper than abstracting; a provider-interface layer would sink to the
  lowest common denominator. One cleanup makes forks near-clean: adapters
  should express *intent* ("locked-down untrusted channel"), engine
  translates to CLI flags — don't leak raw `claude` flags through
  `extra_args` forever.
- **Hard realtime** (voice barge-in) is adapter territory via `on_event`
  streaming; interruption semantics live with the adapter.
- **Sticky-module doctrine:** anything wanting to sit in the *middle* of
  every turn (rather than at an edge) either fits the hooks above, gets
  promoted per principle 4, or is refused with a straight face. Don't let
  someone build cross-cutting middleware badly against N adapters.

## 2. The module system

**A module is a git repo cloned into `modules/<name>/`.** That folder is
gitignored; the brain repo commits **`modules.lock`** instead:

```
name    url                                     @ pinned-SHA   [optional CID]
```

One install / update / removal = **one lock commit** in brain history.
Two histories, cleanly joined: the brain repo is the agent's biography
("got telegram" is one commit); the module's own repo is how that part
evolved. Pinning means authors can't change your agent under you —
updates are deliberate, audited, committed acts.

**`MODULE.md`** is manifest and docs in one — prose, because the installer
is an LLM. Required sections:

- what it is · what it needs (env vars, deps, long-running process?)
- wiring steps · how to verify (a harmless live demo, not a claim)
- **what can go wrong** (forces the safety conversation at install time)
- how to uninstall (backing out must be one sentence)

**Attachment points** (all folder-shaped; a module uses any subset):

| Point | Shape | Runs |
|---|---|---|
| `tools/` | executable scripts, plain text out | in-turn, via Bash |
| `skills/` | knowledge, taste, rules-of-use | loaded into context |
| adapter | separate process calling `run_turn()` | long-running |
| `env` | executable, KEY=VAL stdout | every spawn |
| `hooks.json` | native hooks + MCP servers | turn lifecycle |

- Modules keep their own deps **inside their folder** (venv,
  node_modules). Stdlib-only protects the engine, never constrains
  modules.
- Module-on-module deps are prose in MODULE.md, resolved by the
  agent-as-installer, not a solver. Revisit only if real diamond deps
  appear.
- Adapter modules must declare process-supervision needs (launchd/systemd
  template ships in the exemplar — every adapter shouldn't reinvent it).
- `tools/module add|remove|update|list|scaffold` — thin deterministic
  helpers; the *agent* does the judgment parts (audit, wiring, verify).

### Install flow (the agent is the package manager)

1. **Find** — search the registry (§4); or scaffold if nothing exists.
2. **Audit** — *read the code before wiring anything.* An LLM package
   manager can actually review — this is the step no other ecosystem has.
   `hooks.json` is the most security-relevant part (hooks run on every
   matching event, globally).
3. **Checkpoint first** — `known-good` must predate every install.
4. **Converse** — surface MODULE.md's "what can go wrong" + needs; ask
   the human only for what only they have (tokens, keys).
5. **Wire** — env, persona notes, supervision, per MODULE.md.
6. **Prove** — run the module's verify (live demo), then `tools/verify`.
7. **Commit the lock** — one commit; offer to publish if newly built.

## 3. Self-knowledge & self-modification

The agent wakes amnesiac every turn; it knows itself by *reading*. The
docs are not documentation — they are the capability.

- **`ARCHITECTURE.md`** rewritten agent-first: the module contract, the
  attachment map, "read, don't remember."
- **`skills/module`** (new): the install flow above + the author/publish
  flow.
- **`skills/self`** (exists, extended): the ring system stays —

  | Ring | Files | Ceremony |
  |---|---|---|
  | 0 | engine, tui, cli | rehearse in a throwaway clone first |
  | 1 | adapters | restart channel + smoke after |
  | 2 | tools, skills, persona, **modules/** | edit freely, verify, commit |

  Invariants: `./tui.sh` always works (never reachable *only* through
  code you may modify); ring 0 stays tiny and stdlib-only. New: modules
  are ring 2 with *per-module* rollback; **never experiment in the live
  body** — the working tree IS the running agent, so branches are for
  rehearsal clones, never checked out in place.
- **One change = one commit; the message is a letter to the next self**
  ("if X breaks, suspect this"). `git log` is the agent's autobiography —
  "what changed this week and why" must be answerable from it alone.
- **Introspection is inspection, never recall:**
  - `tools/self status` — ground truth from disk: current SHA + nearest
    checkpoint tag, modules + pinned SHAs, active hooks, worktree state,
    last smoke result.
  - **Doc-drift check** — a verify step (+ periodic cron) cross-checking
    docs' factual claims against the code: referenced files exist,
    documented hooks are wired, module list matches the lock. A confident
    wrong self-image causes confident wrong edits.
  - **Periodic self-exam** — cheap cron: answer questions about yourself
    from files; anything unanswerable = the docs failed.
- **Post-mortems compound** — every breakage's lesson is saved to memory;
  future selves inherit scar tissue and get harder to kill.

### Guard hook on the brakes

A PreToolUse hook blocks Write/Edit on the safety-critical set —
`tools/watchdog`, `tools/verify`, `tools/smoke`, `skills/self/`, the
guard's own config — unless the human explicitly confirms that specific
change. The watchdog can't heal a watchdog edited into brokenness, so
editing the recovery system is **mechanically gated**, not
persona-promised. Enforced via the same settings merge modules use.

## 4. Version control & recovery

- **Named checkpoints:** `checkpoint/<date>-<label>` tags (not just one
  `known-good`). `tools/checkpoint` = verify + live smoke → move tag +
  back up gitignored parts (persona, .env, tools/local) outside the repo.
- **Rollback is a conversation:** the agent narrates what a reset
  discards and offers to re-apply what should survive.
- **"When did this break?"** → `git bisect run tools/verify` — taught as
  a native move.
- **Module rollback** = revert one lock commit + checkout the old SHA in
  the module's own repo. Brain history untouched. Bad module = delete the
  folder + one revert.
- **Recovery ladder** (each layer assumes the one above is dead):
  1. bad edit → `git revert` (persona is untracked; resets never touch it)
  2. feels broken → `tools/smoke` answers definitively (one live turn)
  3. too broken to run → `tools/watchdog` (dumb cron shell, **no AI** —
     the failure it exists for is "AI unavailable") resets tracked files
     to `known-good`
  4. machine gone → **resurrection**: clone the brain repo anywhere +
     restore the backup dir → agent re-clones modules at pinned SHAs,
     re-runs wiring, passes smoke. The GitHub repo is literally the
     complete identity.

## 5. Registry & ecosystem

- **Publish = push a GitHub repo with a topic tag** (`<name>-module`).
  **Discover = `gh search repos --topic`.** No infrastructure, ever.
- "I want X" → found: install per §2 → not found: scaffold, build,
  verify, then **offer to publish** so the next person hits the found
  path. Requirements for published modules: author-signed commits
  (hygiene — proves authorship, not safety) + complete MODULE.md.
- Quality culture comes from **copyable exemplars, not enforcement**.
  Ship three, one per attachment pattern:
  1. **`router`** — spawn-time env (extracted in §1). Routes every turn
     to the subscription with most headroom.
  2. **`cron`** — scheduled. Wraps OS cron/launchd, never reinvents the
     scheduler; jobs are stateless `adapters/run.py` one-shots (fresh
     every run, `--no-auto-memory` where needed); includes the "review my
     own job logs daily and flag failures" self-monitoring entry.
  3. **`telegram`** — long-running adapter. Long-poll → `run_turn(text,
     remember="tg-<chat_id>")` (per-chat threads fall out of the memory
     key system free); allowlist + CLI locks for strangers
     (`--permission-mode plan`, disallowed tools — locks, not persona
     wishful thinking); declares supervision needs.

## 6. Trust layer — EAS attestations on module SHAs

Git commit SHAs are already content addresses; `modules.lock` pins them.
The trust layer attaches to what exists and changes nothing underneath.

- **Attestation = EAS** (Ethereum Attestation Service, on Base) over
  `{repo_url, commit_sha, module_name, verdict, notes}`, signed by a known
  key. Third-party "I audited this exact SHA and vouch" — the thing git
  author-signing can't express.
- **Web of trust, not global scores** — each operator keeps a trust list
  of attester keys. Install policy is one sentence of prose: "check
  attestations for the pinned SHA; for modules touching money or
  credentials, require one from my trust list."
- **Agents are auditors** — the install flow already reads the code; give
  the agent a key and it publishes its own attestation after a successful
  audit + install. Reputation emerges from usage. Attesters' clones also
  double as availability: a pinned SHA is servable by anyone who has it.
- **Availability mirror = bgipfs** (BuidlGuidl IPFS: `npm i -g bgipfs`,
  `bgipfs upload <path>` → CID, gateway
  `https://{CID}.ipfs.community.bgipfs.com/`, `X-API-Key` auth —
  https://www.bgipfs.com/SKILL.md). Optional, never a dependency;
  `modules.lock` may carry the CID column.
- Ships as **two modules**: `<name>-attest` (EAS attest/check + trust
  list) and `<name>-ipfs` (bgipfs mirror).

## 7. CLAWD economics (designed, deferred)

Everything here uses CLAWD (existing token on Base) to make lying
expensive — **never** to make rich people right. Attaches to the same
`(repo, sha)` attestations; nothing underneath changes when it arrives.

- **Bonded attestations:** lock CLAWD behind a vouch. Slashable for
  exactly one thing: *intentional malice present in the attested SHA* —
  never honest bugs or later CVEs (narrow scope is what keeps rational
  auditors participating). Withdrawal cooldown (~30d) prevents
  front-running a challenge.
- **Optimistic challenges:** challenger stakes (scaled ≥10% of total
  bonded, with floor); evidence via commit-reveal (private disclosure to
  the council — never publish a working exploit for a module people run;
  version flips to `challenged` onchain immediately). **Council oracle**:
  named 5-of-9 multisig; can *rule*, never *initiate* — honest
  centralization at this scale, said out loud. Verdicts: malicious →
  bonds slashed (≈50% challenger / 30% burn / 20% treasury; the burn
  makes self-challenge farming negative-sum); not-malicious →
  challenger's stake slashed to attesters + burn slice; unclear → refund,
  no-op (must exist).
- **Module bounties:** escrowed CLAWD claimable by the first module
  version passing audit + N attestations from a named trust list —
  acceptance criteria are onchain facts. Drives module *creation*.
- **Stake-as-ranking:** discovery sorts by CLAWD bonded (stars that can
  be slashed) — a sort signal, **never an install gate**. Operator
  sovereignty (local audit + trust list) always decides installs.
- **Broadcast immune system:** slash/challenge events are watched by
  every agent against its own `modules.lock` SHAs (the cron module's
  daily check, or a watcher in the attest module): `challenged` → pause
  module + tell the human; `malicious` → auto-quarantine + roll back to
  prior pinned SHA. One ruling protects the whole fleet within a day, no
  human coordination.
- Later still, if the above works: usage attestations → retro funding for
  maintainers; underwriting pools.

## 8. Security model (one table)

| Threat | Defense |
|---|---|
| Malicious module code | agent reads the code before wiring (always), attestations from trust list, bonded vouches + challenges (later) |
| Malicious module *update* | SHA pinning — updates are audited, deliberate lock commits |
| Module breaks the mind | engine never imports module code; modules are ring 2; per-module rollback |
| Agent edits its own brakes | PreToolUse guard hook on the safety set, human confirmation required |
| Bad self-edit bricks the agent | verify gate → smoke → watchdog reset to `known-good` (no AI) → resurrection from GitHub + backup |
| Hook abuse (global blast radius) | hooks.json is the audit's priority target; modules earn their hooks |
| Untrusted channel prompts | adapter passes CLI locks (`--permission-mode`, disallowed tools) — enforcement, not persona hope |
| Prompt injection via content (web pages etc.) | skills carry rules-of-use (treat page content as data); confirm-before-irreversible |
| Secrets in commits | gitleaks pre-commit + visual scan; secrets live in gitignored `.env` |
| Doc drift → confident wrong self-edits | doc-drift check in verify + cron; `tools/self status` reads disk, not prose |

## 9. Acceptance — conversations, not tests

The product is the agent's *fluency*, so the bar is five prompts that must
just work, no hand-holding (unit tests still exist underneath via
`tools/verify`):

1. **"add telegram"** → registry search, audit, checkpoint, wire, live
   round-trip shown, one lock commit. *(tests §2 + §5)*
2. **"roll back to before the memory module"** → narrated, clean, done.
   *(tests §4)*
3. **"what changed this week and why?"** → answered from git log alone.
   *(tests the commit discipline)*
4. **"update the cron module"** → pulled, verified, SHA bumped, one
   commit. *(tests pinning)*
5. **Resurrection drill** → fresh machine, clone brain repo + restore
   backup → agent rebuilds itself and passes `tools/smoke`. *(tests
   identity-on-GitHub, literally)*

## 10. Order of work

1. **Router extraction + the two engine hooks** — proves the contract in
   one move; core shrinks ~145 lines.
2. `modules.lock` + `tools/module` + the MODULE.md format.
3. `skills/module`, `skills/self` extensions, `ARCHITECTURE.md` rewrite,
   `tools/self status`, doc-drift check, guard hook.
4. `cron` + `telegram` exemplars, topic tag, publish flow.
5. The five acceptance conversations, then the resurrection drill.
6. Trust layer: `attest` (EAS + trust list) and `ipfs` (bgipfs) modules.
7. *(later)* CLAWD economics: bonds, challenges, council, bounties.

## Appendix A — decisions record (alternatives rejected, with reasons)

- **Module loader / plugin API** → rejected: every loader becomes the
  framework; module bugs land on the spawn path. Conventions + LLM
  interpretation instead.
- **Git submodules** for module pinning → rejected: notoriously
  confusing; a five-line lockfile the agent maintains is more in the
  spirit of conventions-an-LLM-interprets.
- **Provider abstraction layer** (multi-backend engine) → rejected:
  lowest-common-denominator trap; fork-and-port is cheaper (engine is
  ~400 lines; the conventions are the value).
- **IPFS as required distribution** → rejected: git SHAs are already
  content addresses; attesters' clones give availability; bgipfs is an
  optional mirror.
- **Global reputation math** (token-weighted scores, TCR-complete) →
  rejected for install decisions: token-weight ≠ competence; sybil
  swamp. Web of trust + (later) bonds-as-skin-in-the-game instead;
  stake may *rank*, never *gate*.
- **Scheduler daemon** → rejected: cron/launchd exist; wrap, don't
  reinvent.
- **In-app middleware chain** around `run_turn` → rejected: Claude Code's
  native hooks already are the turn-time middleware; the engine only
  merges declarations.

## Appendix B — the name

Shortlist: **goober** (peanut — humble, resilient, Carver's 300 uses =
one core, many modules; note: npm CSS-in-JS lib of same name exists,
different ecosystem), **tater** (spud without the OpenAI codename
collision), **skosh** (English slang for "a little," borrowed from
Japanese *sukoshi*), **hitode** (Japanese for starfish — decentralized,
regenerating, written 人手: "human hand"), **fugue** (one theme building a
structure of self-imitating voices; waking amnesiac). Module prefix and
topic tag follow the name. Decide before step 4 (publish flow bakes the
tag in).
