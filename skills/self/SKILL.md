---
name: self
description: >-
  Modify yourself without breaking yourself — the ring rules, the change
  protocol, and the recovery story. Use whenever editing this agent's own
  code, tools, skills, or persona.
---

# Self-modification

You are `claude -p` spawned fresh in this directory every turn. Your body is
these files; the next turn wakes up in whatever you leave behind. So a change
is safe when the *next* spawn survives it — that's what everything below
protects.

**Know yourself by reading, not remembering.** When unsure what you have or
how something works, read the file — `ls tools/`, `git log`, `ARCHITECTURE.md`.
Never answer from memory; a stale self-image causes confident wrong edits.
When a self-change teaches you a lesson (especially a breakage), save the
post-mortem to your auto-memory so future selves inherit it.

## Rings — how much ceremony a change needs

| Ring | Files | If it breaks | Rule |
|---|---|---|---|
| 0 | `agent.py`, `tui.sh`, `adapters/cli.py` | you can't run *to fix yourself* | rehearse in a clone first |
| 1 | other adapters | one channel dies, mind survives | restart it + `tools/smoke` after |
| 2 | `tools/`, `skills/`, `CLAUDE.md` | one bad task | edit freely, verify, commit |

The closer a file is to the spawn path, the more ceremony. Two invariants:
**`./tui.sh` must always work** (you must never be reachable only through code
you're allowed to modify), and **ring 0 stays tiny and stdlib-only** (zero
dependencies is a survival trait).

## The change protocol

1. Ring 0 only: rehearse — `git clone . /tmp/rehearsal && cd /tmp/rehearsal`,
   apply the change there, `tools/verify` must pass, then apply for real.
2. Make the change.
3. `tools/verify` — compile + unit tests (free, no claude spend).
4. `git commit` — small and often; git is the undo button.
5. `tools/checkpoint` — runs verify + a live smoke turn, then moves the
   `known-good` tag to HEAD and backs up your gitignored parts
   (`CLAUDE.md`, `.env`, `tools/local/`) outside the repo.

## Recovery, from inside out

- A bad edit → `git revert` / `git reset` (your persona is untracked; resets
  never touch it).
- You feel broken → `tools/smoke` says definitively (one live turn, exit code).
- You're too broken to run → `tools/watchdog` (a dumb cron shell script — no
  AI, because the failure it exists for is "AI unavailable") resets tracked
  files to `known-good` on its own.
- Machine is gone → the pushed repo restores code; the checkpoint backup dir
  (`~/.claude-p-agent-backup/`) restores the gitignored persona.
