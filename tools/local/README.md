# tools/local — your private tool overlay

Drop your agent's **private** tools here. Everything in this directory is
**gitignored** (except this README), so tools that are specific to your setup —
ones that hit a particular API, drive your machine, or carry your account's
conventions — never land in the (public) repo.

The split:

| Goes in `tools/` (committed) | Goes in `tools/local/` (gitignored) |
|---|---|
| Generic, shareable, no private endpoints | Specific to your accounts/services/host |
| Example: `note`, a generic `build` | Example: a client for *your* internal API |

Wiring is identical to any other tool: make it executable (`chmod +x`) and
describe it in your `CLAUDE.md` (also gitignored) by its path, e.g.
`tools/local/<name>`. The agent shells out to it like any other tool.

Runtime state these tools generate (token caches, registries, logs) is also
ignored automatically, since the whole directory is — so a tool can safely cache
next to itself.
