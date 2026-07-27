"""tools/vitals — runtime self-knowledge from the live transcript."""
import json
import os
import re
import subprocess
import sys
import unittest
import tempfile

HOME = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VITALS = os.path.join(HOME, "tools", "vitals")


def run_vitals(cwd, env_extra):
    # strip inherited kernel stamps: when verify runs INSIDE an agent turn,
    # the live CLAUDE_P_* env would leak into the "not spawned" scenarios
    env = {k: v for k, v in os.environ.items()
           if not k.startswith("CLAUDE_P_")}
    env.update(env_extra)
    r = subprocess.run([sys.executable, VITALS], cwd=cwd, env=env,
                       capture_output=True, text=True)
    return r.returncode, r.stdout


class TestVitals(unittest.TestCase):
    def test_reads_model_and_context_from_transcript(self):
        with tempfile.TemporaryDirectory() as tmp:
            work = os.path.join(tmp, "work")
            cfg = os.path.join(tmp, "cfg")
            slug = re.sub(r"[^A-Za-z0-9]", "-", os.path.realpath(work))
            pdir = os.path.join(cfg, "projects", slug)
            os.makedirs(work)
            os.makedirs(pdir)
            usage = {"input_tokens": 1000, "cache_read_input_tokens": 49000,
                     "cache_creation_input_tokens": 0, "output_tokens": 0}
            with open(os.path.join(pdir, "abc-123.jsonl"), "w") as f:
                f.write(json.dumps({"type": "user"}) + "\n")
                f.write(json.dumps({"type": "assistant", "message": {
                    "model": "claude-test-1", "usage": usage}}) + "\n")
            code, out = run_vitals(work, {"CLAUDE_CONFIG_DIR": cfg,
                                          "CLAUDE_P_CONTEXT_WINDOW": "200000",
                                          "CLAUDE_P_ENGINE": "claude",
                                          "CLAUDE_P_REMEMBER": "tg-42",
                                          "CLAUDE_P_AUTO_MEMORY": "1",
                                          "CLAUDE_P_ROUTER_PLAN": "cfg"})
            self.assertEqual(code, 0)
            self.assertIn("conversation: persistent — remember key 'tg-42', "
                          "auto-memory on", out)
            self.assertIn("model: claude-test-1", out)
            self.assertIn("~50k / 200k tokens (25% full)", out)
            self.assertIn("session: abc-123", out)
            self.assertIn(f"subscription: cfg ({cfg})", out)
            self.assertIn("router-chosen", out)

    def test_external_engine_reports_engine_model(self):
        with tempfile.TemporaryDirectory() as tmp:
            work = os.path.join(tmp, "work")
            os.makedirs(work)
            code, out = run_vitals(work, {"CLAUDE_CONFIG_DIR": tmp,
                                          "CLAUDE_P_ENGINE": "engine-ollama",
                                          "CLAUDE_P_ENGINE_MODEL": "qwen3:4b"})
            self.assertEqual(code, 0)
            self.assertIn("model: qwen3:4b (external engine)", out)
            self.assertNotIn("claude-", out.split("model:")[1])

    def test_degrades_without_transcript(self):
        with tempfile.TemporaryDirectory() as tmp:
            work = os.path.join(tmp, "work")
            os.makedirs(work)
            code, out = run_vitals(work, {"CLAUDE_CONFIG_DIR": tmp})
            self.assertEqual(code, 0)
            self.assertIn("session: unknown", out)
            self.assertIn("engine: claude (built-in)", out)
            self.assertIn("conversation: unknown (not spawned via agent.py", out)


if __name__ == "__main__":
    unittest.main()
