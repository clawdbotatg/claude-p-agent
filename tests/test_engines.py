"""test_engines — the external-engine protocol (v0), without any real LLM.

Pins the contract from PLAN-ENGINES.md: an engine is `modules/<name>/engine`,
one JSON request on stdin, JSONL events on stdout, last line
{"type":"result","text","state"}. The kernel owns keys and stores the opaque
state blob per engine; claude-only options hard-error; forget() clears engine
state too; installing an engine never activates it (selection is explicit).
"""
import json
import os
import stat
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import agent  # noqa: E402

# A fake engine: echoes the text uppercased, reports the system prompt it was
# handed, counts turns in its state blob, and emits one non-result event first.
FAKE_ENGINE = """#!/usr/bin/env python3
import json, sys
req = json.load(sys.stdin)
n = (req.get("state") or {}).get("n", 0) + 1
print(json.dumps({"type": "delta", "n": n}))
print(json.dumps({
    "type": "result",
    "text": f'{req["text"].upper()} n={n} sys={req.get("system", "")}',
    "state": {"n": n},
}))
"""

BROKEN_ENGINE = """#!/usr/bin/env python3
import sys
print("not json at all")
sys.exit(3)
"""


def write_exec(path, body):
    with open(path, "w", encoding="utf-8") as f:
        f.write(body)
    os.chmod(path, os.stat(path).st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


class EngineProtocolTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.modules = os.path.join(self.tmp, "modules")
        os.makedirs(self.modules)
        self._prev = {
            "MODULES_DIR": agent.MODULES_DIR,
            "AGENT_DIR": agent.AGENT_DIR,
            "home": os.environ.get("CLAUDE_P_AGENT_HOME"),
            "memory": os.environ.get("CLAUDE_P_AGENT_MEMORY"),
            "engine": os.environ.get("ENGINE"),
        }
        agent.MODULES_DIR = self.modules
        agent.AGENT_DIR = self.tmp
        os.environ["CLAUDE_P_AGENT_HOME"] = self.tmp
        os.environ["CLAUDE_P_AGENT_MEMORY"] = os.path.join(self.tmp, ".memory")
        os.environ.pop("ENGINE", None)
        d = os.path.join(self.modules, "fake")
        os.makedirs(d)
        write_exec(os.path.join(d, "engine"), FAKE_ENGINE)

    def tearDown(self):
        agent.MODULES_DIR = self._prev["MODULES_DIR"]
        agent.AGENT_DIR = self._prev["AGENT_DIR"]
        for env, key in (("CLAUDE_P_AGENT_HOME", "home"),
                         ("CLAUDE_P_AGENT_MEMORY", "memory"),
                         ("ENGINE", "engine")):
            if self._prev[key] is None:
                os.environ.pop(env, None)
            else:
                os.environ[env] = self._prev[key]

    # ── dispatch ─────────────────────────────────────────────────────────

    def test_missing_engine_raises(self):
        with self.assertRaisesRegex(RuntimeError, "not installed"):
            agent.run_turn("hi", engine="nope")

    def test_env_var_selects_engine(self):
        os.environ["ENGINE"] = "fake"
        self.assertIn("HI n=1", agent.run_turn("hi"))

    def test_param_overrides_env(self):
        os.environ["ENGINE"] = "nope"
        self.assertIn("HI n=1", agent.run_turn("hi", engine="fake"))

    # ── the turn ─────────────────────────────────────────────────────────

    def test_oneshot_returns_text_and_stores_nothing(self):
        out = agent.run_turn("hello", engine="fake")
        self.assertIn("HELLO n=1", out)
        self.assertFalse(agent._engine_state_paths("anything"))

    def test_persona_and_append_reach_system(self):
        with open(os.path.join(self.tmp, "CLAUDE.md"), "w", encoding="utf-8") as f:
            f.write("I am the persona.")
        out = agent.run_turn("hi", engine="fake", append_system_prompt="channel policy")
        self.assertIn("I am the persona.", out)
        self.assertIn("channel policy", out)

    def test_events_stream_to_on_event(self):
        events = []
        agent.run_turn("hi", engine="fake", on_event=events.append)
        self.assertEqual([e["type"] for e in events], ["delta", "result"])

    def test_return_meta_shape(self):
        out = agent.run_turn("hi", engine="fake", return_meta=True)
        self.assertIn("HI n=1", out["text"])
        self.assertIsNone(out["session_id"])

    def test_broken_engine_raises_with_stderr_exit(self):
        d = os.path.join(self.modules, "broken")
        os.makedirs(d)
        write_exec(os.path.join(d, "engine"), BROKEN_ENGINE)
        with self.assertRaisesRegex(RuntimeError, "exited 3"):
            agent.run_turn("hi", engine="broken")

    # ── memory: kernel keys, engine blobs, per-engine namespace ─────────

    def test_state_round_trips_per_key(self):
        self.assertIn("n=1", agent.run_turn("hi", engine="fake", remember="alice"))
        self.assertIn("n=2", agent.run_turn("hi", engine="fake", remember="alice"))
        self.assertIn("n=1", agent.run_turn("hi", engine="fake", remember="bob"))
        path = agent._engine_state_path("alice", "fake")
        with open(path, encoding="utf-8") as f:
            self.assertEqual(json.load(f), {"n": 2})

    def test_forget_clears_engine_state(self):
        agent.run_turn("hi", engine="fake", remember="alice")
        self.assertTrue(agent.forget("alice"))
        self.assertIn("n=1", agent.run_turn("hi", engine="fake", remember="alice"))

    # ── claude-only options refuse loudly ────────────────────────────────

    def test_extra_args_refused(self):
        with self.assertRaisesRegex(RuntimeError, "extra_args"):
            agent.run_turn("hi", engine="fake", extra_args=["--tool", "Read"])

    def test_session_id_refused(self):
        with self.assertRaisesRegex(RuntimeError, "session_id"):
            agent.run_turn("hi", engine="fake", session_id="abc123")

    def test_input_via_refused(self):
        with self.assertRaisesRegex(RuntimeError, "input_via"):
            agent.run_turn("hi", engine="fake", input_via="stdin")


if __name__ == "__main__":
    unittest.main()
