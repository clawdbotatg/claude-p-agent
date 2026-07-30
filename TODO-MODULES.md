# Module & engine ideas — the build-next list

Published so far: `router`, `cron`, `telegram`, `ipfs`, `attest`,
`engine-oai`, `engine-ollama`. Each future module should do double duty:
be useful, and **teach a pattern someone can copy**. Ordered by what it
proves, not by size.

Registry: GitHub topic `claude-p-agent-module`. Build flow: `tools/module
scaffold NAME` → fill MODULE.md → `tools/module publish NAME` (see
`skills/module`).

---

## Teaches an unused extension point

### 1. `mcp-example` — the canonical mcpServers demo
Nothing yet ships `mcpServers` in a `hooks.json`, so the fourth attachment
point is undemonstrated. Smallest useful stateful MCP server.
- **Example:** a sqlite key-value store: `kv set deploy-block "waiting on
  Austin"`, `kv get deploy-block` — state that survives across turns and
  conversation keys without touching the persona.
- **Example:** a counter/quota server — "how many times have I done X
  today" — the primitive every rate-limited behavior needs.

### 2. `model-router` — right model for the right ask
An env hook that sets `ANTHROPIC_MODEL` per turn. Proves the env hook can
do more than subscription routing (its output merges into the child env —
that's the whole trick, same as `router`).
- **Example:** cron-spawned turns (env var set by the cron module's caller)
  get haiku; interactive turns get the default model.
- **Example:** a keyword escalator — the adapter passes
  `MODEL_HINT=deep` in env for "think hard about…" asks; hook maps hint →
  opus-class model.

### 3. `skills-pack` — a module with no code at all
Ships only `skills/`. Proves the lowest possible contribution bar.
- **Example:** `code-review` — a review checklist skill the agent applies
  when asked to review a PR.
- **Example:** `voice-style` — a writing/speaking style guide (short
  sentences for TTS channels) any persona can adopt.

## Teaches composition (modules using modules)

### 4. `backup` — disaster recovery, composed from cron + ipfs
Periodic snapshot of the untracked identity (persona `CLAUDE.md`, `.env`
key *names* (never values), `modules.lock`, `.memory/` index) pushed to
IPFS via the `ipfs` module; restore instructions in MODULE.md. First
module that *depends on* two others — forces us to show how MODULE.md
declares dependencies.
- **Example:** nightly cron entry → `backup snapshot` → pinned CID logged;
  `backup restore <cid>` walks the resurrection path from a bare clone.
- **Example:** pre-checkpoint hook use: `tools/checkpoint` already backs up
  locally; `backup` adds the offsite copy.

### 5. `digest` — cheap-model journalism, composed from cron + an engine
A scheduled summary written by a cheap engine (engine-oai/engine-ollama)
and delivered via telegram. Demonstrates "right model for the right job"
as a module and engine selection per task.
- **Example:** morning digest — RSS/news/repo activity summarized by
  qwen3:14b locally, one telegram message at 8am.
- **Example:** weekly self-digest — "what did my agent change about itself
  this week" from `git log` + checkpoint tags, written by a local model.

## Broad demand / new capability class

### 6. `journal` — long-term memory beyond auto-memory
Structured daily notes + `remember`/`recall` tools + a search skill. The
most-asked-for agent feature in the wild.
- **Example:** `journal note "met with X about Y"` → dated markdown;
  `journal search Y` → hits with dates; a skill teaches the agent to
  journal significant events unprompted and consult it before answering
  "when did we…" questions.
- **Example:** weekly synthesis cron: distill the week's notes into a
  summary page (composes with `cron`, optionally a cheap engine).

### 7. `wallet` — read-only v0, the trust-loop showcase
Balances, tx history, ENS resolution on Base/mainnet via Alchemy (never
public RPCs; key in `.env`). Holds no private keys — v0 signs nothing,
same stance as `attest`. This is deliberately the module where the
attestation docs get exercised for real: money-adjacent, so the install
audit's "zero trusted attestations — here's my audit" flow is the demo.
- **Example:** `wallet balance vitalik.eth`, `wallet txs 0x… --limit 10`.
- **Example:** telegram alert (composes cron): "wallet X received > 0.1
  ETH" — watch-only treasury monitoring.

### 8. `discord` (or `email`) — the second channel
Mostly to prove the `telegram` adapter pattern generalizes: long-running
process importing the engine, trust-tagged channel policy via
`append_system_prompt`, `remember=<channel-id>`.
- **Example:** discord bot with per-channel conversation keys; DMs get the
  private-channel policy, public channels the guarded one.
- **Example (email flavor):** IMAP poll via cron → each thread is a
  conversation key; reply drafts only (human sends) as the safe v0.

---

## Engine wishlist (same seam, different brains)

- **`engine-codex` / `engine-gemini-cli`** — wrap other *agentic CLIs*
  non-interactively, the way the kernel wraps `claude -p`. The strongest
  proof the pattern is vendor-neutral: tools-capable bodies on other
  vendors' subscriptions. Build `engine-codex` first.
- **Tools mode for `engine-oai`** — port engine-ollama's bash-tool loop to
  cloud models (qwen3-coder with a shell, for pennies). Same loud safety
  caveats: no guard hook on external-engine turns.
- **`engine-anthropic-api`** — Anthropic Messages API with a metered key:
  serves people with an API key but no subscription; cheap haiku turns for
  chores. A real engine (different wire shape), unlike…
- **Not engines: recipes.** OpenRouter, Groq, Gemini-compat, LM Studio,
  llama.cpp, vLLM are all just `.env` configs for `engine-oai` — document
  copy-paste blocks in engine-oai's MODULE.md instead of cloning it.

## The name (parked decision)

Everything is `claude-p-*` until the project gets its real name. Shortlist
(from the original plan): **goober** (peanut — humble, resilient; Carver's
300 uses = one core, many modules; an npm CSS-in-JS lib shares the name,
different ecosystem), **tater**, **skosh** ("a little," from Japanese
*sukoshi*), **hitode** (starfish — decentralized, regenerating; written
人手, "human hand"), **fugue** (one theme, self-imitating voices; the
waking amnesiac). Module prefix and registry topic follow the name.

## Notes that apply to all of these

- Money- or credential-touching modules (`wallet`, `email`) must lead
  their MODULE.md with **What can go wrong** and are the priority targets
  for the attest loop (get real attestations on them early).
- Anything spawning unattended turns (`digest`, `backup`, watchers)
  defaults to stateless one-shots (`--no-auto-memory` where cleanliness
  matters) per the memory doctrine in `README.md`.
- Prefer composing existing modules over new machinery — `backup` and
  `digest` exist partly to prove composition works and document its
  MODULE.md conventions.
