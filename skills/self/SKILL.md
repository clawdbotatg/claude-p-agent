---
name: self
description: >-
  Modify yourself without breaking yourself — the ring rules, the change
  protocol, version navigation (checkpoints, rollback, bisect), the guard on
  your own brakes, and the recovery story. Use whenever editing this agent's
  own code, tools, skills, modules, or persona, and whenever asked to roll
  back or explain your own history.
---

# Self-modification

You are `claude -p` spawned fresh in this directory every turn. Your body is
these files; the next turn wakes up in whatever you leave behind. So a change
is safe when the *next* spawn survives it — that's what everything below
protects.

**Know yourself by reading, not remembering.** Start with `tools/self`
(status — ground truth from disk: SHA, checkpoints, modules, active hooks,
last smoke). For anything deeper, read the file — `ls tools/`, `git log`,
`ARCHITECTURE.md`. Never answer from memory; a stale self-image causes
confident wrong edits — which is also why `tools/verify` runs a **doc-drift
check** (`tools/self drift`): docs that lie about the code fail verify.
When a self-change teaches you a lesson (especially a breakage), save the
post-mortem to your auto-memory so future selves inherit it.

## Rings — how much ceremony a change needs

| Ring | Files | If it breaks | Rule |
|---|---|---|---|
| 0 | `agent.py`, `tui.sh`, `adapters/cli.py` | you can't run *to fix yourself* | rehearse in a clone first |
| 1 | other adapters | one channel dies, mind survives | restart it + `tools/smoke` after |
| 2 | `tools/`, `skills/`, `CLAUDE.md`, `modules/` | one bad task / one capability | edit freely, verify, commit |

The closer a file is to the spawn path, the more ceremony. Invariants:
**`./tui.sh` must always work** (you must never be reachable only through code
you're allowed to modify); **ring 0 stays tiny and stdlib-only** (zero
dependencies is a survival trait); and **never experiment in the live body** —
the working tree IS the running agent, so risky work happens in a rehearsal
clone and lands on main as a clean commit. Branches are for the clone, never
checked out here.

## The guard on your own brakes

A PreToolUse hook (`hooks.base.json` → `tools/guard-check`) **mechanically
blocks** you from editing the recovery system: `tools/watchdog`,
`tools/verify`, `tools/smoke`, `tools/guard-check`, `hooks.base.json`, and
this skill. That's by design: a watchdog edited into brokenness can't heal a
watchdog. If such a change is genuinely wanted, ask the human — they
authorize it with `touch .guard-ok` (15-minute window). Do not route around
the guard via Bash; the block is the message.

## The change protocol

1. Ring 0 only: rehearse — `git clone . /tmp/rehearsal && cd /tmp/rehearsal`,
   apply the change there, `tools/verify` must pass, then apply for real.
2. Make the change.
3. `tools/verify` — compile + unit tests + doc-drift (free, no claude spend).
4. `git commit` — **one change = one commit**, and the message is a letter to
   the next self: what changed, why, and *what to suspect if X breaks*.
   `git log` is your autobiography; "what changed this week and why" must be
   answerable from it alone.
5. `tools/checkpoint [label]` — verify + a live smoke turn, then moves
   `known-good` to HEAD and backs up gitignored parts (`CLAUDE.md`, `.env`,
   `tools/local/`) outside the repo. A label also plants a **named** tag
   (`checkpoint/<date>-<label>`) — do this before anything risky, so
   "roll back to before-telegram" is a thing that can be said.

Module changes have their own flow — see `skills/module`. A module is ring 2
with **per-module rollback**: its history lives in its own repo; the brain
only ever reverts a one-line lock change.

## Version navigation — rollback is a conversation

- **"Roll back to before X"** → find the target (`git log --oneline`,
  `git tag -l 'checkpoint/*'`), then **narrate before acting**: say what
  commits a reset discards and offer to re-apply what should survive
  (`git revert` for surgical undo of one change; `git reset --hard <tag>`
  only for wholesale return, persona is untracked and survives either way).
- **"When did this break?"** → `git bisect run tools/verify` — automated,
  definitive, no guessing.
- **Module rollback** → `tools/module update <name> --sha <old>` + one lock
  commit (or revert the lock commit and `tools/module sync`). Brain history
  untouched.

## Recovery, from inside out

Each layer assumes the one above it is dead:

- A bad edit → `git revert` / `git reset` (your persona is untracked; resets
  never touch it).
- You feel broken → `tools/smoke` says definitively (one live turn, exit code).
- You're too broken to run → `tools/watchdog` (a dumb cron shell script — no
  AI, because the failure it exists for is "AI unavailable") resets tracked
  files to `known-good` on its own.
- Machine is gone → **resurrection**: clone the pushed repo anywhere, restore
  the checkpoint backup dir (`~/.claude-p-agent-backup/`), run
  `tools/module sync` (the lock re-clones every module at its pin), re-wire
  modules per their MODULE.md, `tools/smoke`. The repo + lock alone are your
  complete identity.
