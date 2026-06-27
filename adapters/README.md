# Adapters

An adapter maps a message source → `run_turn(...)`.

**Shipped:** `cli.py` only (terminal TUI). Launched via `./tui.sh`.

**Yours to add:** Telegram, web UI, Slack, cron, voice bridge, etc. The engine stays
dumb; you pass `append_system_prompt` and `extra_args` from adapter-owned prompt files.

Read **`skills/extend/SKILL.md`** for patterns and a minimal code sketch.

```python
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from agent import run_turn

reply = run_turn(user_text, on_event=...)  # trusted keyboard — no extra prompt
```

Reference implementations in other repos:

- Voice: [clawd-video-chat/cc-bridge.py](https://github.com/clawdbotatg/clawd-video-chat)
