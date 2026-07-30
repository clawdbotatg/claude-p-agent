# Engine protocol v0 — the contract

An agent is a **persona + an engine + modules, in a directory**. Claude
Code is the built-in engine (inside `agent.py`, ring 0 — recovery never
depends on the module system). An **external engine** is a module repo
shipping one executable, `modules/<name>/engine`, speaking the protocol
below. Prove one with `tools/engine-check <name>`.

```
adapters      where a message came from        (telegram, tui, cron)
   ↓ run_turn(text, remember=, engine=, …)
kernel        keys, modules, persona, spawn     (agent.py)
   ↓ one JSON request in, JSONL events out
engine        LLM + turn loop + state blob      (executable module repo)
```

## The wire

Request — one JSON object on stdin (read it fully before writing):

```json
{
  "v": 0,
  "text": "the user message",
  "system": "persona text + adapter channel policy, joined",
  "state": null,
  "agent_dir": "/abs/path",
  "options": {}
}
```

Response — JSONL on stdout; every line is an event (forwarded to
`on_event`); the **last line must be**:

```json
{"type": "result", "text": "the reply", "state": {"…engine-defined…"}}
```

Non-zero exit or no result line = engine error (stderr is the message).
Cwd = the engine's module dir; child env = the scrubbed,
module-env-hooked env (router etc. keep working under every engine).

## The rules

- **State is an opaque engine-defined blob**, stored by the kernel per
  conversation key, namespaced per engine
  (`.memory/<key>@<engine>.state`). Same key on a different engine = a
  fresh thread, by design; no cross-engine porting. For a raw chat API
  the blob is simply the message history.
- **Install ≠ activate.** The active engine is named explicitly —
  `ENGINE=<name>` in `.env` or `run_turn(engine=…)`. Default: `claude`.
- **Refuse, never drop.** Claude-only options (`extra_args`,
  `session_id`, `input_via`) hard-error on external engines. An engine
  must refuse any `options` entry it can't honor.
- **No parity emulation.** Chat engines have no tools, files, or cwd —
  declare it and degrade loudly (never pretend). Claude Code auto-memory
  is a claude-engine capability, not reimplemented. Ring-0
  self-modification stays on the claude engine regardless of `ENGINE`.
- **Trust like any module**: pinned SHA in `modules.lock`, code audited,
  attestable via `attest`, rebuilt by `tools/module sync`.

## Existing engines

- [claude-p-engine-oai](https://github.com/clawdbotatg/claude-p-engine-oai)
  — any OpenAI-style `/chat/completions` route (OpenRouter, Groq, Bankr,
  api.openai.com, local servers) via env config.
- [claude-p-engine-ollama](https://github.com/clawdbotatg/claude-p-engine-ollama)
  — local Ollama, self-healing server, optional supervised bash-tool loop.

Wanted next (see `TODO-MODULES.md`): engine-codex / engine-gemini-cli
(wrap other agentic CLIs the way the kernel wraps `claude -p`),
engine-anthropic-api (metered key, no subscription).
