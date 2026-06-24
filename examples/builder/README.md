# example: builder — a self-improving agent

This is the template filled in by a real, useful agent — with **no ties to any
service, account, or machine**, so you can run it as-is and read every line.

**builder** is `claude -p` in a directory whose one tool, `build`, spawns *more*
Claude Code sessions to write software. That single move is the whole thesis of
this repo turned up to its logical end:

- **Chat is `claude -p`.** Every turn the owner has with builder is one
  `run_turn()` call (see `../../agent.py`).
- **Building is Claude Code sessions.** builder never edits files in its own turn;
  `tools/build` launches a fresh `claude` session in the target directory to do the
  work, in isolation, on your subscription.
- **Self-improvement is the same move, pointed inward.** `build run . "<task>"`
  aims builder's hands at its own directory — so it writes its own new tools and
  edits its own `CLAUDE.md`. The agent that builds software can build *itself*.

## What to look at

- **`CLAUDE.md`** — the persona. Note the order: *identity* first ("a senior
  engineer who ships"), then the self-improvement framing, then tools, then the
  channel/trust model. And notice how self-improvement and the trust model fit
  together: changing code is a **private-only** power, so the same boundary that
  stops a stranger from deploying also stops a stranger from rewriting the agent.

- **`tools/build`** — the one tool that matters here. ~110 lines, no external
  service. It demonstrates two things the rest of the repo only talks about:
  1. **Delegation to Claude Code sessions** — `build run <dir> "<task>"` spawns a
     headless `claude` worker; `build worktree <repo> "<task>"` runs it in a
     throwaway branch you review before merging.
  2. **The env-scrub billing gotcha**, in practice — it scrubs the same vars
     `agent.py` does, because a child `claude` that inherits them silently flips to
     metered API billing with no transcript.

## Try it

From the repo root, run builder instead of the default agent by pointing the
engine at this directory:

```bash
AGENT_DIR=examples/builder python3 adapters/cli.py
> add a tool called `weather` that prints a fake forecast, then tell me about it
```

builder will `build run . "..."`, a Claude Code session will write
`examples/builder/tools/weather`, and builder will report back — having just
extended itself. Lock the public channel down in `.env` (`CLAUDE_ARGS_PUBLIC`) and
you'll see the same request refused over `--public`, because building is private.

## Nothing real lives here

By the template's own rule, this example carries no secrets, accounts, paths, or
service names — it's pure mechanics. Make it yours by pointing `build` at your own
repos and giving builder a notes dir (`BRAIN_DIRS`) so each build starts smarter
than the last.
