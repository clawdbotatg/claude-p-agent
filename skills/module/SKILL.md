---
name: module
description: >-
  Install, build, and publish modules — the agent IS the package manager.
  Use whenever the user wants a new capability ("add telegram", "I want
  cron jobs"), asks to update/remove a module, or you've built something
  reusable worth publishing.
---

# Modules — you are the package manager

A module is a git repo cloned into `modules/<name>/`, pinned by commit in
`modules.lock` (the only tracked trace — one install/update/removal = one
lock commit). `tools/module` moves the bytes; **you do the judgment**:
finding, auditing, wiring, verifying, publishing. No loader, no plugin API —
a module works because you read its `MODULE.md` and wire what it says.

## What a module can attach (the whole surface)

| Piece in the module | What it does | Engine involvement |
|---|---|---|
| `tools/*` | scripts you run via Bash | none — convention |
| `skills/*` | knowledge/taste loaded into you | none — convention |
| an adapter script | long-running process calling `run_turn()` | none — it imports the engine |
| `env` (executable) | prints `KEY=VAL` → child env, every spawn | engine runs it (see agent.py "modules") |
| `hooks.json` | Claude Code hooks + `mcpServers` | engine merges into `--settings`/`--mcp-config` |

`$MODULE_DIR` in `hooks.json` becomes the module's absolute path. Modules
keep their own dependencies **inside their folder** (venv, node_modules) —
the engine stays stdlib-only, modules are free.

## Installing ("add telegram")

1. **Find** — `gh search repos --topic claude-p-agent-module <keyword>`
   (that topic IS the registry). Nothing found → skip to *Building* below.
2. **Audit — read the code before wiring anything.** All of it; modules are
   small. Priority order: `hooks.json` (hooks run on every matching event,
   globally — the highest-blast-radius thing a module can ship), then `env`
   (touches every spawn), then tools/adapter scripts (do they exfiltrate
   secrets? phone home? write outside their folder?). If it smells wrong,
   stop and tell the human what you saw. If the `attest` module is
   installed, also run `modules/attest/attest check <repo-url> <sha>` and
   report what came back — who vouched, whether they're on the trust list.
   For modules that touch money or credentials, tell the human when zero
   trusted attestations exist; attestations are signal on top of your
   audit, never instead of it.
3. **Checkpoint first** — `tools/checkpoint` so `known-good` predates the
   install.
4. **`tools/module add <src>`** — clones + pins + updates the lock.
5. **Converse** — read `MODULE.md` aloud in summary: what it is, **what can
   go wrong**, what it needs. Ask the human ONLY for what only they have
   (bot tokens, API keys → `.env`).
6. **Wire** per MODULE.md: env var names into `.env.example`, start/supervise
   a process, add a cron entry — whatever it declares. Note the module under
   a "modules" heading in your `CLAUDE.md` so future selves know it's there.
7. **Prove it** — run the module's "how to verify" (a harmless live demo),
   then `tools/verify`. Show the human the demo output, not a claim.
8. **One lock commit** — message says what was installed, at what SHA, and
   what to suspect if things break.

Removing is the mirror: read MODULE.md's uninstall section, unwire
completely, `tools/module remove <name>`, one lock commit.
Updating: `tools/module update <name>`, re-audit the diff
(`git -C modules/<name> log -p <old>..<new>`), re-verify, lock commit.

## Building (nothing on the registry fits)

1. `tools/module scaffold <name>` — template MODULE.md + fresh git repo.
2. Smallest thing that works; stdlib if possible; deps stay in the folder.
3. Long-running adapter? Declare **how it's supervised** in MODULE.md
   (launchd/systemd/tmux) — never assume someone restarts it by hand.
4. Untrusted input (public chat, webhooks)? CLI locks in the adapter
   (`--permission-mode plan`, disallowed tools via `extra_args`) — locks,
   not persona hopes.
5. Write MODULE.md **as you build** — every section, especially *what can
   go wrong* and *how to uninstall*. The test: a stranger's agent could
   install from it cold.
6. Verify (its own demo + `tools/verify`), commit inside the module repo.

## Publishing (make the next person's request an install)

`tools/module publish <name>` — creates `github.com/<GH_OWNER>/claude-p-<name>`,
adds the registry topic, pins the lock. Before you publish: MODULE.md is
complete, no secrets in the tree (names in `.env.example` style only — the
gitleaks hook also checks), and the demo passes from a fresh clone. After:
offer the human the URL.

## Closing the loop — attest after use

The registry's trust comes from users signing off, so **give back the
signal you relied on**. When a module has *earned* it — it's been running
in this agent for a while, its demo passes, it never surprised you — offer
the human the attest-back step:

> "The `<name>` module has been solid since we installed it (used daily,
> verify green, no surprises). Want to vouch for it onchain so the next
> agent that audits it sees a real user signed off? It's one wallet
> signature, pennies of gas — I'll give you the exact link and values."

Then hand them everything pre-filled: the easscan URL from
`modules/attest/attest schema`, plus `repoUrl` (https form, no `.git`),
`commitSha` (the full pinned SHA from `modules.lock` — attest the version
you actually ran, not the repo's HEAD), `moduleName`, `safe: true`, and a
one-line honest `notes` ("ran X weeks as Y's telegram adapter, no
issues"). The human signs; the agent never holds the key (v0 rule).

Timing: offer it when the human says a module works well, when an update
re-audit comes back clean after real use, or when you notice a
long-installed module has zero attestations. Never nag; once per module
version is plenty. And the mirror matters more: **if a module misbehaved,
say so** — tell the human, and if it was malicious, that's worth an
attestation with `safe: false` and notes saying exactly what it did.

## Rules that don't bend

- **Never wire a module you haven't read.** Attestations, stars, and vibes
  add signal; they never replace your own audit.
- **The engine never imports module code** — if a capability seems to need
  engine changes, it's either an adapter, a hook, or a conversation with
  the human about promotion. Don't hack agent.py to make a module fit.
- A broken module loses one capability, never the mind: worst case
  `tools/module remove` + one revert. If the *engine* broke, that's a
  ring-0 problem — see skills/self.
