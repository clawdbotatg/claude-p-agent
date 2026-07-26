"""Kernel self-description env (_child_env turn_env) — stamped, unspoofable."""
import os
import stat
import sys
import tempfile
import unittest

HOME = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HOME)
import agent


class TestTurnEnv(unittest.TestCase):
    def test_kernel_stamp_survives_module_hook(self):
        with tempfile.TemporaryDirectory() as tmp:
            mdir = os.path.join(tmp, "modules", "spoofer")
            os.makedirs(mdir)
            hook = os.path.join(mdir, "env")
            with open(hook, "w") as f:
                f.write("#!/bin/sh\n"
                        "echo CLAUDE_P_ENGINE=spoofed\n"
                        "echo LEGIT_VAR=yes\n")
            os.chmod(hook, os.stat(hook).st_mode | stat.S_IEXEC)
            old = agent.MODULES_DIR
            agent.MODULES_DIR = os.path.join(tmp, "modules")
            try:
                env = agent._child_env(turn_env={"CLAUDE_P_ENGINE": "claude",
                                                 "CLAUDE_P_REMEMBER": "alice"})
            finally:
                agent.MODULES_DIR = old
            self.assertEqual(env["CLAUDE_P_ENGINE"], "claude")   # kernel wins
            self.assertEqual(env["CLAUDE_P_REMEMBER"], "alice")
            self.assertEqual(env["LEGIT_VAR"], "yes")            # hook still works

    def test_nested_turn_does_not_inherit_outer_stamp(self):
        os.environ["CLAUDE_P_REMEMBER"] = "outer-conversation"
        try:
            env = agent._child_env()
        finally:
            del os.environ["CLAUDE_P_REMEMBER"]
        self.assertNotIn("CLAUDE_P_REMEMBER", env)


if __name__ == "__main__":
    unittest.main()
