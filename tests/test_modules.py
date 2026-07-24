"""test_modules — the engine's two extension points, without spawning claude.

Pins the contract modules rely on: env hooks merge KEY=VAL stdout (empty value
removes, garbage/failures ignored, later module wins), and hooks.json /
hooks.base.json declarations merge into generated --settings / --mcp-config
files with $MODULE_DIR / $AGENT_HOME substituted.
"""
import json
import os
import stat
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import agent  # noqa: E402


def write_exec(path, body):
    with open(path, "w", encoding="utf-8") as f:
        f.write(body)
    os.chmod(path, os.stat(path).st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


class ModuleLayerTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.modules = os.path.join(self.tmp, "modules")
        os.makedirs(self.modules)
        self._prev_modules_dir = agent.MODULES_DIR
        agent.MODULES_DIR = self.modules
        self._prev_home = os.environ.get("CLAUDE_P_AGENT_HOME")
        os.environ["CLAUDE_P_AGENT_HOME"] = self.tmp

    def tearDown(self):
        agent.MODULES_DIR = self._prev_modules_dir
        if self._prev_home is None:
            os.environ.pop("CLAUDE_P_AGENT_HOME", None)
        else:
            os.environ["CLAUDE_P_AGENT_HOME"] = self._prev_home

    def module(self, name):
        d = os.path.join(self.modules, name)
        os.makedirs(d, exist_ok=True)
        return d

    # ── env hook ─────────────────────────────────────────────────────────

    def test_env_hook_merges_and_removes(self):
        d = self.module("alpha")
        write_exec(os.path.join(d, "env"),
                   "#!/bin/sh\n"
                   "echo FOO=bar\n"
                   "echo GONE=\n"
                   "echo 'this is not a kv line'\n"
                   "echo BAD KEY=x\n")
        env = {"GONE": "yes", "PATH": os.environ.get("PATH", "")}
        agent._apply_module_env(env)
        self.assertEqual(env.get("FOO"), "bar")
        self.assertNotIn("GONE", env)
        self.assertNotIn("this is not a kv line", str(env.keys()))

    def test_env_hook_failure_is_ignored(self):
        d = self.module("broken")
        write_exec(os.path.join(d, "env"), "#!/bin/sh\necho FOO=nope\nexit 1\n")
        env = {"PATH": os.environ.get("PATH", "")}
        agent._apply_module_env(env)
        self.assertNotIn("FOO", env)

    def test_non_executable_env_is_skipped(self):
        d = self.module("passive")
        with open(os.path.join(d, "env"), "w", encoding="utf-8") as f:
            f.write("#!/bin/sh\necho FOO=nope\n")
        os.chmod(os.path.join(d, "env"), 0o644)
        env = {"PATH": os.environ.get("PATH", "")}
        agent._apply_module_env(env)
        self.assertNotIn("FOO", env)

    def test_later_module_wins_alphabetically(self):
        write_exec(os.path.join(self.module("aaa"), "env"), "#!/bin/sh\necho K=first\n")
        write_exec(os.path.join(self.module("zzz"), "env"), "#!/bin/sh\necho K=second\n")
        env = {"PATH": os.environ.get("PATH", "")}
        agent._apply_module_env(env)
        self.assertEqual(env.get("K"), "second")

    def test_hook_sees_current_env_and_runs_in_module_dir(self):
        d = self.module("aware")
        write_exec(os.path.join(d, "env"),
                   "#!/bin/sh\n"
                   "echo SAW=$UPSTREAM\n"
                   "echo WHERE=$(basename \"$PWD\")\n")
        env = {"UPSTREAM": "hello", "PATH": os.environ.get("PATH", "")}
        agent._apply_module_env(env)
        self.assertEqual(env.get("SAW"), "hello")
        self.assertEqual(env.get("WHERE"), "aware")

    def test_no_modules_dir_is_a_noop(self):
        agent.MODULES_DIR = os.path.join(self.tmp, "missing")
        env = {"PATH": os.environ.get("PATH", "")}
        agent._apply_module_env(env)
        self.assertEqual(set(env), {"PATH"})

    # ── settings merge ───────────────────────────────────────────────────

    def test_hooks_json_merges_with_module_dir_substituted(self):
        d = self.module("guardish")
        with open(os.path.join(d, "hooks.json"), "w", encoding="utf-8") as f:
            json.dump({"hooks": {"PreToolUse": [
                {"matcher": "Write|Edit",
                 "hooks": [{"type": "command", "command": "$MODULE_DIR/check"}]}
            ]}}, f)
        hooks, mcp = agent._merged_module_settings()
        cmd = hooks["PreToolUse"][0]["hooks"][0]["command"]
        self.assertEqual(cmd, os.path.join(d, "check"))
        self.assertEqual(mcp, {})

    def test_base_file_merges_first_with_agent_home(self):
        with open(os.path.join(self.tmp, "hooks.base.json"), "w", encoding="utf-8") as f:
            f.write(json.dumps({"hooks": {"PreToolUse": [
                {"matcher": "Write", "hooks": [
                    {"type": "command", "command": "$AGENT_HOME/tools/guard-check"}]}
            ]}}))
        d = self.module("m1")
        with open(os.path.join(d, "hooks.json"), "w", encoding="utf-8") as f:
            json.dump({"hooks": {"PreToolUse": [
                {"matcher": "Bash", "hooks": [{"type": "command", "command": "x"}]}
            ]}}, f)
        hooks, _ = agent._merged_module_settings()
        self.assertEqual(len(hooks["PreToolUse"]), 2)
        self.assertIn(os.path.join(self.tmp, "tools", "guard-check"),
                      hooks["PreToolUse"][0]["hooks"][0]["command"])

    def test_mcp_servers_merge_and_flags_written(self):
        d = self.module("statef")
        with open(os.path.join(d, "hooks.json"), "w", encoding="utf-8") as f:
            json.dump({"mcpServers": {"browser": {
                "command": "$MODULE_DIR/serve", "args": []}}}, f)
        flags = agent._module_settings_flags()
        self.assertIn("--mcp-config", flags)
        gen = flags[flags.index("--mcp-config") + 1]
        with open(gen, encoding="utf-8") as f:
            data = json.load(f)
        self.assertEqual(data["mcpServers"]["browser"]["command"],
                         os.path.join(d, "serve"))
        self.assertNotIn("--settings", flags)

    def test_bad_json_is_ignored(self):
        d = self.module("junk")
        with open(os.path.join(d, "hooks.json"), "w", encoding="utf-8") as f:
            f.write("{not json")
        hooks, mcp = agent._merged_module_settings()
        self.assertEqual((hooks, mcp), ({}, {}))

    def test_no_declarations_no_flags(self):
        self.assertEqual(agent._module_settings_flags(), [])


if __name__ == "__main__":
    unittest.main()
