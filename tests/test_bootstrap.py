"""First-run CLAUDE.md bootstrap."""
import importlib.util
import os
import tempfile
import unittest

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CLI = os.path.join(HERE, "adapters", "cli.py")
EXAMPLE = os.path.join(HERE, "CLAUDE.md.example")


def load_cli():
    spec = importlib.util.spec_from_file_location("cli", CLI)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class PersonalizeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cli = load_cli()

    def test_replaces_name_and_todos(self):
        with open(EXAMPLE, encoding="utf-8") as f:
            raw = f.read()
        out = self.cli.personalize_claude_md(raw, "Larry")
        self.assertIn("# You are Larry", out)
        self.assertNotIn("<AGENT NAME>", out)
        self.assertNotIn("TODO: one short paragraph", out)
        self.assertIn("Friendly and concise", out)


if __name__ == "__main__":
    unittest.main()
