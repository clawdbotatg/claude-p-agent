"""test_memory — the one memory system's plumbing: key resolution + persistence.

These don't spawn claude (that's the live smoke test); they pin the contract that
adapters rely on — a key maps to a stable file, write/read/forget round-trips, and a
path-shaped key pins its own location.
"""
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import agent  # noqa: E402


class MemoryTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self._prev = os.environ.get("CLAUDE_P_AGENT_MEMORY")
        os.environ["CLAUDE_P_AGENT_MEMORY"] = self.tmp

    def tearDown(self):
        if self._prev is None:
            os.environ.pop("CLAUDE_P_AGENT_MEMORY", None)
        else:
            os.environ["CLAUDE_P_AGENT_MEMORY"] = self._prev

    def test_name_key_lives_in_memory_root(self):
        p = agent._memory_path("alice")
        self.assertEqual(os.path.dirname(p), os.path.abspath(self.tmp))
        self.assertTrue(p.endswith("alice.session"))

    def test_same_key_same_file(self):
        self.assertEqual(agent._memory_path("bob"), agent._memory_path("bob"))

    def test_path_shaped_key_is_literal(self):
        path = os.path.join(self.tmp, "sub", "x.session")
        self.assertEqual(agent._memory_path(path), os.path.abspath(path))

    def test_unsafe_key_is_sanitized(self):
        p = agent._memory_path("../../etc/passwd")  # has '/', treated as a path, not escaping the root concept
        self.assertTrue(p)  # resolves without raising
        p2 = agent._memory_path("a b:c*d")  # plain name → sanitized
        self.assertNotIn(" ", os.path.basename(p2))
        self.assertNotIn(":", os.path.basename(p2))

    def test_write_read_forget_roundtrip(self):
        path = agent._memory_path("conv1")
        self.assertIsNone(agent._read_session(path))
        agent._write_session(path, "sess-abc-123")
        self.assertEqual(agent._read_session(path), "sess-abc-123")
        self.assertTrue(agent.forget("conv1"))
        self.assertIsNone(agent._read_session(path))
        self.assertFalse(agent.forget("conv1"))  # already gone

    def test_parse_json_result(self):
        text, sid = agent._parse_json_result('{"result": "hi", "session_id": "s1"}')
        self.assertEqual((text, sid), ("hi", "s1"))
        text, sid = agent._parse_json_result("not json")
        self.assertEqual((text, sid), ("not json", None))


if __name__ == "__main__":
    unittest.main()
