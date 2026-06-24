# tools

A **tool** is a CLI script your agent shells out to. That's the whole concept.
There is no plugin API, no registration, no schema. If your agent can run it in
a shell and read its output, it's a tool.

Why this works: Claude Code already has a Bash tool. So "giving your agent a new
capability" is just "writing a script and mentioning it in `CLAUDE.md`." The
agent reads the description, runs the command, reads the result.

## The shape

```
tool <verb> [args...]   →   plain text on stdout
```

Keep them small and single-purpose. Print human-readable text (the agent reads
it like you would). Read secrets from `$ENV_VARS`, never hardcode them. Exit
non-zero with a message on misuse.

## What's here

| Tool | What it does |
|---|---|
| `note` | a trivial scratch notebook — the minimal example of a tool |

## A tool that does real work

See `examples/builder/tools/build` — the same "CLI script → plain text" shape, but
it spawns a fresh Claude Code session in a directory to build software (and, pointed
at the agent's own dir, to improve the agent itself). Same shape, the most
interesting job: your agent's hands.

## Shared vs. private tools

- **`tools/`** (here) — generic, shareable tools that carry no private endpoints.
  Committed.
- **`tools/local/`** — your agent's private tools: ones tied to your accounts,
  services, or host. **Gitignored**, so they never reach the (public) repo. See
  `tools/local/README.md`. Reference them from your `CLAUDE.md` by path, e.g.
  `tools/local/<name>` — wiring is identical.

## Wiring a tool in

1. Drop the script in `tools/`, make it executable (`chmod +x`).
2. Describe it in `CLAUDE.md` under "your tools" — name, what it does, when to
   use it. That description is the only thing that tells the agent it exists.
3. If it needs secrets, add them to `.env` (and `.env.example`) and read them
   from the environment.
