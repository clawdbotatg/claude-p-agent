"""./setup — persona bootstrap; non-interactive runs never spawn claude."""
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

HOME = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class TestSetup(unittest.TestCase):
    def run_setup(self, tmp, stdin):
        return subprocess.run([sys.executable, os.path.join(tmp, "setup")],
                              input=stdin, capture_output=True, text=True,
                              cwd=tmp, timeout=60)

    def test_bootstrap_is_light_and_idempotent(self):
        with tempfile.TemporaryDirectory() as tmp:
            for rel in ("setup", "CLAUDE.md.example", "modules.lock"):
                shutil.copy(os.path.join(HOME, rel), tmp)
            r = self.run_setup(tmp, "TestBot\n")
            self.assertEqual(r.returncode, 0, r.stderr)
            with open(os.path.join(tmp, "CLAUDE.md")) as f:
                persona = f.read()
            self.assertIn("You are TestBot", persona)
            self.assertNotIn("<!--", persona)             # banner stripped
            # piped stdin → no first conversation, no claude spawn, no modules
            self.assertIn("skipping the first conversation", r.stdout)
            self.assertFalse(os.path.isdir(os.path.join(tmp, "modules")))
            self.assertFalse(os.path.isdir(os.path.join(tmp, ".memory")))

            r2 = self.run_setup(tmp, "")
            self.assertEqual(r2.returncode, 0, r2.stderr)
            self.assertIn("already exists — keeping it", r2.stdout)


if __name__ == "__main__":
    unittest.main()
