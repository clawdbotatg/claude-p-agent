# adapters

An **adapter** is the only part of the system that knows where a message came
from. Its entire contract is:

```python
from agent import run_turn
reply = run_turn(text, trust)   # trust ∈ {"public", "private"}
```

It decides two things and nothing else:

1. **`text`** — the message to hand the agent.
2. **`trust`** — `"private"` if the source is authenticated as the owner,
   `"public"` otherwise. When unsure, use `"public"`.

That's the whole interface. The agent doesn't know or care whether a message
came from a terminal, a browser, a phone call, a webhook, or a chat bot — only
how much to trust it. So you can run the *same* agent behind many front-ends at
once, each mapping its source to the right trust level.

## What's here

| Adapter | Source | Trust |
|---|---|---|
| `cli.py` | your terminal | `private` (or `--public` to simulate untrusted) |

## Writing your own

A web adapter, a Telegram bot, a voice loop — all the same shape. Authenticate
the source however that medium allows (a token, a signature, a known chat id),
map "authenticated as owner" → `private` and everything else → `public`, then
call `run_turn`. Keep auth in the adapter; keep persona in `CLAUDE.md`; keep the
trust *policy* in `prompts/`.

> Tip: the trust split is only as strong as its weakest enforcement. The
> `prompts/` files state the policy, but back them with CLI permission flags per
> channel (`CLAUDE_ARGS_PUBLIC`, `CLAUDE_ARGS_PRIVATE` in `.env`) so an untrusted
> channel physically cannot call dangerous tools.
