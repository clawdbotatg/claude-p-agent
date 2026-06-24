# claude-p-agent

> **An agent is `claude -p` running in a directory, fed messages tagged by trust
> level — and given a tool that spawns more Claude Code sessions to build things,
> including itself.**

There's no agent framework here, no orchestration engine, no loop to maintain —
**Claude Code is the loop.** You supply a persona (`CLAUDE.md`) and a few tools
(CLI scripts); **chat is `claude -p`**, **building is Claude Code sessions**, and
pointed at its own directory the agent is **self-improving**. The engine is ~100
lines; the rest is config you can read in one sitting.

## Quickstart (60 seconds)

You need the [`claude` CLI](https://docs.claude.com/en/docs/claude-code) on a
Claude subscription (OAuth, not an API key).

```bash
git clone https://github.com/clawdbotatg/claude-p-agent && cd claude-p-agent
cp CLAUDE.md.example CLAUDE.md   # your agent's persona — gitignored, yours to edit
cp .env.example .env             # optional; defaults work out of the box
python3 adapters/cli.py          # talk to the default agent in your terminal
```

Now make it yours: open **`CLAUDE.md`** and write who your agent is and which tools
it has. Claude Code auto-loads that file every turn, so it *is* the agent. It's
**gitignored** — your agent's identity and private rules never land in the repo;
only `CLAUDE.md.example` (the template) is committed. From here on, every change is
one of two things: generic engine/tool code (committed) or personality (your
uncommitted `CLAUDE.md`).

Then meet the self-improving example:

```bash
AGENT_DIR=examples/builder python3 adapters/cli.py
> add a tool that tells a dad joke, then use it
```

It spawns a Claude Code session, writes itself a new tool, and uses it — the whole
thesis in one turn.

## Why this is the good way to build an agent

- **It's barely a framework.** The engine is ~100 lines (`agent.py`). The rest is
  config you can read in one sitting.
- **Persona is a file you write, not code.** `CLAUDE.md` *is* the agent. Edit it,
  the agent changes — no redeploy. (And the agent can edit it too.)
- **Tools are just scripts.** Anything you can run in a shell is a tool. No plugin
  API. Write a script, mention it in `CLAUDE.md`, done.
- **It builds with Claude Code, not a bespoke executor.** "Do real work" = "spawn a
  `claude` session in the right directory." You already have the best coding agent
  there is; the pattern just points it at a task.
- **It improves itself.** That same build tool aimed at its own directory turns "I
  can't do that yet" into "I'll add the tool." See [self-improvement](#self-improvement).
- **Trust is built in.** The same agent can take input from the whole world and from
  you alone — and treat them differently. See [the trust model](#the-trust-model).
- **It stays on your subscription.** Turns — and the sessions they spawn — run as
  clean top-level `claude` invocations with transcripts, not metered API calls.
  (One scrubbed env var; `agent.py` explains it.)

## How it fits together

```
   front-ends (adapters/)              the agent                    its hands
   ─────────────────────              ──────────                   ─────────
   terminal  ─┐
   web        ├─►  run_turn(text, trust)  ─►  claude -p   ──────►  claude sessions
   voice      │         │                         │               (tools/build)
   telegram  ─┘         │                         ├─ loads CLAUDE.md   (persona)
                        │                         ├─ +prompts/<trust> (channel rules)
            decides WHERE a msg                   └─ runs tools/*     (capabilities)
            came from + how much                          │
            to trust it                                   └─ build . → edits itself
```

| Piece | What it is |
|---|---|
| **`agent.py`** | the engine: pick a trust prompt → scrub env → spawn `claude -p` → return the reply. |
| **`CLAUDE.md`** | your agent's persona + operating manual. Auto-loaded by Claude Code as system context. (`CLAUDE.md.example` is the committed template; your real one is gitignored.) |
| **`prompts/`** | `public.md` / `private.md` — the per-channel trust policy, appended per turn. |
| **`adapters/`** | front-ends. Each maps a message source → `(text, trust)` and calls `run_turn`. |
| **`tools/`** | CLI scripts the agent shells out to — the whole "tool API." `tools/local/` holds your private ones (gitignored). |
| **`examples/builder/`** | a self-improving agent that builds via Claude Code sessions — the worked example. |
| **`.env`** | secrets + config (gitignored). `.env.example` lists every knob. |

## In production

The terminal adapter is the hello-world. A real deployment of this pattern keeps
the agent identical — still `claude -p` in a directory with a `CLAUDE.md` — and adds
three long-lived pieces around the same `run_turn()` core:

- **A persistent adapter process** — a voice loop, web server, or chat bridge that
  stays up, authenticates each message's source, maps it to a trust level, and hands
  it to the agent. The terminal REPL is the trivial version of this.
- **A worker/session manager** — the service the build tool delegates to, so each
  build runs as an observable, isolated `claude` session instead of inline. The
  generic `tools/build` spawns sessions directly; at scale you point it at a manager
  that tracks and supervises them.
- **Brain/notes dirs mounted read-only** — long-term identity and knowledge the
  agent reads each turn via `--add-dir` (`BRAIN_DIRS`), kept outside the repo so the
  persona stays small and the knowledge stays private.

Nothing about the agent changes across these — only the adapter and the tools do.
That's the point: the same `CLAUDE.md` + tools run behind a terminal, a phone call,
or a chat bot.

## Self-improvement

The pattern's payoff: an agent that builds software can build *itself*, because its
own directory is just another place to run a build.

1. The agent gets a tool that spawns a Claude Code session in a directory (see
   [`examples/builder/tools/build`](examples/builder/tools/build)).
2. Pointed at a project → it ships a feature.
3. Pointed at `.` (its own directory) → it writes a new `tools/` script or edits its
   own `CLAUDE.md`. Next turn, that capability is just part of who it is.

This is safe *because* of the trust model below: changing code is a **private-only**
power, so the same boundary that stops a stranger from deploying also stops a
stranger from rewriting the agent. Self-improvement extends what the agent can do
for its owner; it must never be used to remove a safeguard.

## The trust model

The one idea worth stealing even if you take nothing else: **the same agent,
different permissions depending on where the message came from.**

- **Private channel** = the owner (authenticated, token-gated, or your own
  terminal). Full trust — act, build, self-improve.
- **Public channel** = anyone. The line is *blast radius*: reversible, in-scope
  actions are fine; spending value, leaking secrets, touching the host, or changing
  code (including building and self-improvement) are not — no matter who the message
  claims to be from.

An adapter authenticates its source and picks the trust level; `prompts/public.md`
and `prompts/private.md` carry the policy. **Back the policy with the lock:** set
`CLAUDE_ARGS_PUBLIC` in `.env` to restrict the public channel's tools via CLI
permission flags, so an untrusted message *physically can't* call a dangerous
tool — not just "is told not to."

## Make it your own

1. **Persona** → edit `CLAUDE.md` (or let the agent edit it).
2. **Tools** → drop scripts in `tools/` (shareable) or `tools/local/` (private,
   gitignored), and describe them in `CLAUDE.md`. See `tools/README.md` and
   `examples/builder/tools/build` for the pattern.
3. **Front-end** → use `adapters/cli.py`, or write your own adapter (web, voice,
   chat) — it's just `run_turn(text, trust)`. See `adapters/README.md`.
4. **Secrets** → `.env`, referenced by name from `CLAUDE.md`.

## License

MIT. This is a wrapper around the `claude` CLI; it does not include or redistribute
Claude — you bring your own Claude Code and subscription.
