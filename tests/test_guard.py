"""test_guard — the agent may not edit its own brakes (tools/guard-check).

Runs the hook as Claude Code would: JSON on stdin, exit code is the verdict
(0 allow, 2 block). The override flag file is exercised and cleaned up.
"""
import json
import os
import subprocess
import sys
import unittest

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GUARD = os.path.join(HERE, "tools", "guard-check")
FLAG = os.path.join(HERE, ".guard-ok")


def run_guard(payload, env_extra=None):
    env = dict(os.environ)
    env.update(env_extra or {})
    r = subprocess.run(
        [sys.executable, GUARD],
        input=payload if isinstance(payload, str) else json.dumps(payload),
        capture_output=True, text=True, env=env,
    )
    return r.returncode, r.stderr


def edit_payload(path):
    return {"tool_name": "Edit", "tool_input": {"file_path": path}}


class GuardTest(unittest.TestCase):
    def tearDown(self):
        try:
            os.remove(FLAG)
        except OSError:
            pass

    def test_blocks_protected_files(self):
        for rel in ("tools/watchdog", "tools/verify", "tools/smoke",
                    "tools/guard-check", "hooks.base.json",
                    "skills/self/SKILL.md"):
            code, err = run_guard(edit_payload(os.path.join(HERE, rel)))
            self.assertEqual(code, 2, f"{rel} should be blocked")
            self.assertIn("BLOCKED", err)

    def test_allows_normal_files(self):
        for rel in ("agent.py", "tools/module", "skills/extend/SKILL.md",
                    "README.md", "modules.lock"):
            code, _ = run_guard(edit_payload(os.path.join(HERE, rel)))
            self.assertEqual(code, 0, f"{rel} should be allowed")

    def test_fresh_override_allows(self):
        with open(FLAG, "w", encoding="utf-8"):
            pass
        code, err = run_guard(edit_payload(os.path.join(HERE, "tools/verify")))
        self.assertEqual(code, 0)
        self.assertIn("override", err)

    def test_stale_override_blocks(self):
        with open(FLAG, "w", encoding="utf-8"):
            pass
        old = os.stat(FLAG).st_mtime - 3600
        os.utime(FLAG, (old, old))
        code, _ = run_guard(edit_payload(os.path.join(HERE, "tools/verify")))
        self.assertEqual(code, 2)

    def test_garbage_stdin_allows(self):
        code, _ = run_guard("this is not json")
        self.assertEqual(code, 0)

    def test_no_file_path_allows(self):
        code, _ = run_guard({"tool_name": "Bash",
                             "tool_input": {"command": "ls"}})
        self.assertEqual(code, 0)


if __name__ == "__main__":
    unittest.main()
