# Adapters

An adapter maps a message source → `run_turn(...)`. The engine has no trust tiers;
you pass `append_system_prompt` and `extra_args` from adapter-owned prompt files.

```python
import sys, os
sys.path.insert(0, os.environ.get("CLAUDE_P_AGENT_HOME", "/path/to/claude-p-agent"))
from agent import read_prompt, run_turn

reply = run_turn(
    text,
    append_system_prompt=read_prompt("adapters/prompts/public.md"),
    extra_args=["--permission-mode", "plan"],
)
```

| Adapter | Channel policy |
|---|---|
| `cli.py` | owner keyboard (none) or `--public` → `adapters/prompts/public.md` |
| `telegram.py` | owner DM → `private.md`; else → `public.md` + `CLAUDE_ARGS_PUBLIC` |

See `ARCHITECTURE.md`. Video-chat adapter lives in `clawd-video-chat/cc-bridge.py`.
