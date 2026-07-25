# Plan: pluggable engines

> Companion to `PLAN.md`. That doc's thesis is "an agent is `claude -p` in a
> directory, with a persona and tools." This doc takes the next step: **an
> agent is a persona + an engine + modules, in a directory — signed all the
> way down.** Claude Code stays the primary engine; it stops being the only
> possible one.

## 0. Why

Today `agent.py` *is* the Claude Code engine. If you want the same brain —
same persona, same modules, same memory keys, same adapters — running on
Codex, on an OpenAI-style API route (Bankr, OpenRouter), or on some CLI that
doesn't exist yet, there is no seam to swap at. This plan cuts that seam,
using machinery the repo already has (modules, lock, attestations) instead
of inventing new machinery.

## 1. The decomposition

`run_turn()` currently does seven jobs. Only some are Claude-specific:

| Job | Where it lands |
|---|---|
| `.env` loading, `AGENT_DIR`, cwd | kernel (engine-neutral) |
| module env hooks (`modules/*/env`) | kernel (they just emit env vars) |
| memory **keying** (`remember=` → load/save/forget) | kernel |
| persona custody (owning the text) | kernel |
| env scrub, CLI flag syntax, session ids, stream format | engine |
| persona **delivery** (CLAUDE.md auto-load vs system message) | engine |
| hooks/MCP declaration translation | engine (kernel merges, engine translates) |

So the layering settles as:

```
adapters      where a message came from        (telegram, tui, cron)
   ↓ run_turn(text, remember=, engine=, …)
kernel        keys, modules, persona, spawn     (agent.py — tiny, ring 0)
   ↓ one JSON request in, JSONL events out
engine        LLM + turn loop + state blob      (executable; external ones
                                                 are signed module repos)
```

`run_turn()`'s signature is the stable contract — no adapter changes when an
engine is added.

## 2. Engines are executables, not imports

The law "the engine never imports module code" survives because an engine is
an **executable speaking a dumb protocol**, exactly the same shape as
spawning `claude -p` today — the kernel just stops hardcoding which
executable and whose wire format.

**Protocol v0** (deliberately minimal; version field for later growth):

Request — one JSON object on stdin:

```json
{
  "v": 0,
  "text": "the user message",
  "system": "persona text + adapter channel policy, joined",
  "state": null,
  "agent_dir": "/abs/path",
  "options": {}
}
```

`state` is an **opaque engine-defined blob** the kernel stored from the
previous turn on this conversation key (null = fresh). `options` is the
engine-neutral vocabulary (future: `max_turns`, `model`, tool locks) — an
engine must *refuse* an option it can't honor, never silently drop it.

Response — JSONL on stdout. Every line is an event (forwarded to
`on_event`); the **last line must be**:

```json
{"type": "result", "text": "the reply", "state": {"…engine-defined…"}}
```

Non-zero exit or a missing result line = engine error (stderr is the
message). Cwd = the engine's own module dir; child env = the usual scrubbed,
module-env-hooked env, so the router and other env-hook modules keep working
under every engine.

**Trust:** an external engine is a module repo — pinned SHA in
`modules.lock`, auditable, attestable via the `attest` module, resurrected by
`tools/module sync`. One extra gate on top of normal modules: **installing an
engine never activates it.** The active engine is named explicitly —
`ENGINE=<name>` in `.env`, or `run_turn(engine=…)` per call. Default is
`claude`, the built-in.

**The built-in `claude` engine stays inside `agent.py`** (ring 0, stdlib,
byte-identical to today's behavior). Rationale: the recovery story ("the mind
always spawns", `./tui.sh` must always work) cannot depend on a module dir
that `module sync` might need to rebuild. External engines get the seam;
the reference engine is part of the body.

## 3. Memory — three kinds, three answers, no emulation

The blur dissolves once memory is named precisely. The rule that keeps it
clean: **never emulate a capability an engine lacks. Declare it, degrade
loudly, or refuse.**

1. **Thread memory** (this conversation continues) — the kernel owns the
   *key*; the engine owns the *blob*. Claude's blob is a session id (Claude
   Code keeps the transcript). An API-route engine's blob is the message
   history itself — that's not "reimplementing Claude Code's memory," it's
   just what conversation state *is* for a raw chat API, and it's ~15 lines.
   Blobs are engine-namespaced (`.memory/<key>@<engine>.state`): same key on
   a different engine = a fresh thread, by design. No cross-engine porting.
2. **Durable facts** (Claude Code auto-memory) — a *claude-engine
   capability*, not reimplemented anywhere. If an engine-neutral version is
   ever wanted, it's a **module** that maintains fact files the kernel folds
   into the persona text — possible *because* persona flows through the
   kernel, but explicitly deferred.
3. **Body knowledge** (the repo, docs, git) — already engine-neutral; any
   engine with file tools reads it. API-route engines can't; that's a
   declared limitation, not a gap to fill.

## 4. Persona

The persona *content* is the agent's; the *filename* `CLAUDE.md` is a Claude
Code delivery mechanism. v0: the kernel reads `CLAUDE.md` (if present) and
passes its text as `system` to external engines; the built-in claude engine
keeps auto-load untouched. A later ceremony renames the canonical file to
`PERSONA.md` with `CLAUDE.md` as a symlink — deferred so this plan changes
one thing at a time.

## 5. Capability honesty

An OpenAI-style API engine has **no tools, no files, no cwd** — it is a chat
brain: right for cheap/fast channels (naming, summaries, small talk), wrong
for "edit your own module." Consequences, enforced not documented:

- `extra_args` (raw Claude CLI flags — including the `--tool` locks
  untrusted channels rely on) passed to an external engine → **hard error**,
  never dropped.
- Ring-0 self-modification and `skills/self` ceremonies are pinned to the
  claude engine regardless of `ENGINE`.
- Full agentic alternatives (Codex CLI, opencode→OpenRouter-with-tools) are
  future engine repos under the same protocol; we do **not** hand-roll a
  tool loop over a raw API.

## 6. Routing

Starts dumb and stays dumb until proven otherwise: `ENGINE=` is the default,
adapters/callers override per call (`run.py --engine`, cron jobs pinning a
cheap engine). No AI dispatcher — same restraint as principle 4 in PLAN.md.

## 7. Order of work

1. **This doc** — commit the contract before the code.
2. **Kernel seam** (ring 0, rehearsed in a clone): `ENGINE` env +
   `run_turn(engine=)`, `_run_engine_turn()` speaking protocol v0,
   engine-namespaced state files, hard errors on unportable options.
   Default path byte-identical. Tests: a fake engine in a temp modules dir
   pins the protocol (echo, state round-trip, forget, refusals). Amend
   ARCHITECTURE.md's "exactly two extension points" law to name the engine
   seam as the deliberate third.
3. **First external engine: `engine-oai`** — a generic OpenAI-style
   chat-completions engine (~100 lines, stdlib urllib): `OAI_ENGINE_BASE_URL`
   / `_API_KEY` / `_MODEL` / `_AUTH` (bearer | x-api-key), message-history
   state blob with a truncation cap. Scaffolded, published, locked like any
   module. **Tested live against Bankr** (`llm.bankr.bot`, `X-API-Key`) —
   config, not code; OpenRouter is the same engine with different env.
4. **Later, as separate effort:** Codex engine repo (AGENTS.md delivery,
   `codex exec` sessions), opencode engine repo, options vocabulary growth
   (`model`, `max_turns`, tool locks that map to real sandboxes), the
   durable-facts module, the PERSONA.md rename.

## 8. Decisions record

- **Executable protocol over Python import** — preserves "engine never
  imports module code"; language-agnostic; a broken engine repo can't break
  the spawn of the default engine.
- **Built-in claude engine, not extracted to a repo** — recovery must not
  depend on the module system.
- **Install ≠ activate** — a module becoming the engine is an explicit
  `.env` decision by the operator, never a side effect of `module add`.
- **Per-engine state namespacing over portable transcripts** — porting
  conversation state across engines is a translation project with no
  payoff; honest fresh threads are simpler.
- **No parity emulation** (auto-memory, hooks, tools on chat engines) —
  capability flags + loud refusal beat a half-faithful shim everywhere.
- **Generic `engine-oai` over a bankr-specific engine** — Bankr, OpenRouter,
  and any OpenAI-compatible endpoint are one engine with different env.
