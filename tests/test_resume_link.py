"""test_resume_link — a remembered session resumes under whichever login the
router picks (clawd-twitter's daemon, 2026-09-24: a login with a REAL projects/
dir couldn't see the transcript and every turn died on "No conversation found").
"""
import io
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stderr
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import agent  # noqa: E402

SID = "a5cca576-780a-45c9-b94d-a332e7fb40a4"


class ResumeLinkTest(unittest.TestCase):
    def setUp(self):
        self.home = tempfile.mkdtemp()
        self.accts = os.path.join(self.home, ".clawd-accounts")
        self.main = os.path.join(self.home, ".claude")
        self.lone = os.path.join(self.accts, "lone")        # real projects/ dir
        os.makedirs(os.path.join(self.lone, "projects", "-p"))
        os.makedirs(os.path.join(self.accts, "other"))
        self.patch = mock.patch.dict(os.environ, {"HOME": self.home})
        self.patch.start()

    def tearDown(self):
        self.patch.stop()

    def _write(self, root):
        d = os.path.join(root, "projects", "-p")
        os.makedirs(os.path.join(d, SID, "subagents"), exist_ok=True)
        path = os.path.join(d, SID + ".jsonl")
        open(path, "w").write("{}\n")
        return path

    def test_links_transcript_from_another_login(self):
        src = self._write(self.main)
        sid = agent._ensure_resumable(SID, {"CLAUDE_CONFIG_DIR": self.lone})
        self.assertEqual(sid, SID)
        link = os.path.join(self.lone, "projects", "-p", SID + ".jsonl")
        self.assertEqual(os.path.realpath(link), os.path.realpath(src))
        self.assertTrue(os.path.isdir(os.path.join(self.lone, "projects", "-p", SID)))

    def test_links_from_a_sibling_login_too(self):
        self._write(os.path.join(self.accts, "other"))
        self.assertEqual(agent._ensure_resumable(SID, {"CLAUDE_CONFIG_DIR": self.lone}), SID)

    def test_already_visible_is_untouched(self):
        self._write(self.lone)
        self.assertEqual(agent._ensure_resumable(SID, {"CLAUDE_CONFIG_DIR": self.lone}), SID)

    def test_missing_everywhere_starts_fresh(self):
        err = io.StringIO()
        with redirect_stderr(err):
            sid = agent._ensure_resumable(SID, {"CLAUDE_CONFIG_DIR": self.lone})
        self.assertIsNone(sid)
        self.assertIn("starting fresh", err.getvalue())

    def test_no_session_is_a_noop(self):
        self.assertIsNone(agent._ensure_resumable(None, {}))


if __name__ == "__main__":
    unittest.main()
