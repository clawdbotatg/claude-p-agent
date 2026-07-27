"""./setup — engine-first bootstrap; non-interactive runs never spawn/install."""
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

HOME = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class TestSetup(unittest.TestCase):
    def run_setup(self, tmp, stdin, env=None):
        return subprocess.run([sys.executable, os.path.join(tmp, "setup")],
                              input=stdin, capture_output=True, text=True,
                              cwd=tmp, env=env, timeout=60)

    def copy_repo(self, tmp):
        for rel in ("setup", "CLAUDE.md.example", "modules.lock"):
            shutil.copy(os.path.join(HOME, rel), tmp)
        os.makedirs(os.path.join(tmp, "tools"))
        shutil.copy(os.path.join(HOME, "tools", "module"),
                    os.path.join(tmp, "tools"))

    def test_no_name_question_and_light_default(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.copy_repo(tmp)
            r = self.run_setup(tmp, "")           # zero answers needed
            self.assertEqual(r.returncode, 0, r.stderr)
            with open(os.path.join(tmp, "CLAUDE.md")) as f:
                persona = f.read()
            self.assertIn("You are Agent", persona)   # placeholder, no prompt
            self.assertNotIn("<!--", persona)
            self.assertNotIn("What should your agent be called", r.stdout)
            # piped stdin → no first conversation, no engine spawn, no modules
            self.assertIn("skipping the first conversation", r.stdout)
            self.assertFalse(os.path.isdir(os.path.join(tmp, "modules")))
            self.assertFalse(os.path.isdir(os.path.join(tmp, ".memory")))
            # re-run: still fine, persona untouched
            r2 = self.run_setup(tmp, "")
            self.assertEqual(r2.returncode, 0, r2.stderr)
            with open(os.path.join(tmp, "CLAUDE.md")) as f:
                self.assertEqual(persona, f.read())

    def test_no_claude_machine_wires_nothing_non_interactively(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.copy_repo(tmp)
            env = {k: v for k, v in os.environ.items() if k != "CLAUDE_BIN"}
            env["HOME"] = tmp                      # hide ~/.local/bin/claude
            env["PATH"] = "/usr/bin:/bin"
            r = self.run_setup(tmp, "", env=env)
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertIn("no engine wired", r.stdout)
            self.assertFalse(os.path.isdir(os.path.join(tmp, "modules")))


if __name__ == "__main__":
    unittest.main()
