# tools

A **tool** is a CLI script your agent shells out to. No plugin API — if Claude Code
can run it in Bash and read stdout, it's a tool.

## Shape

```
tool <verb> [args...]   →   plain text on stdout
```

Describe each tool in `CLAUDE.md`. Run `tools/verify` after code changes.

## What's here

| Tool | What it does |
|---|---|
| `verify` | compile all `.py` + run tests — run before saying "fixed" |
| `vitals` | runtime self-knowledge: model, context %, subscription, engine — the agent runs it to answer "what am I right now" |
| `engine-check` | protocol conformance for an engine module (`engine-check NAME`) — run before routing turns to it |

## Private tools

Put agent-specific scripts in **`tools/local/`** (gitignored). Same shape, same wiring.

## Adding tools

Ask your agent to read `skills/extend/SKILL.md`, or add scripts yourself and list them in `CLAUDE.md`.
