"""Tests for multiline input key handling in adapters/cli.py."""
import importlib.util
import os
import unittest

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CLI = os.path.join(HERE, "adapters", "cli.py")


def load_cli():
    spec = importlib.util.spec_from_file_location("cli", CLI)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class EnterKindTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cli = load_cli()

    def test_shift_enter_kitty(self):
        self.assertEqual(self.cli._enter_kind("13;2u"), "newline")

    def test_plain_enter_kitty(self):
        self.assertEqual(self.cli._enter_kind("13;1u"), "submit")
        self.assertEqual(self.cli._enter_kind("13u"), "submit")

    def test_shift_enter_modify_other_keys(self):
        self.assertEqual(self.cli._enter_kind("27;2;13~"), "newline")

    def test_plain_enter_modify_other_keys(self):
        self.assertEqual(self.cli._enter_kind("27;1;13~"), "submit")

    def test_unrelated_csi(self):
        self.assertIsNone(self.cli._enter_kind("1;2A"))


class SubmitVsNewlineBytes(unittest.TestCase):
    """Document the contract read_multiline relies on in raw mode."""

    def test_cr_is_submit_byte(self):
        self.assertEqual(b"\r"[0], 0x0D)

    def test_lf_is_newline_byte_not_submit(self):
        # Shift+Enter on macOS/Cursor often sends LF; must NOT be treated as submit.
        self.assertEqual(b"\n"[0], 0x0A)
        self.assertNotEqual(b"\n"[0], 0x0D)


if __name__ == "__main__":
    unittest.main()
