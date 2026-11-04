"""Tests for the opt-in read guard hook (plugins/gemini/hooks)."""

import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

HOOK = Path(__file__).resolve().parents[1] / "plugins" / "gemini" / "hooks" / "read-guard.sh"


def run_hook(event, mode=None, extra_env=None):
    env = {k: v for k, v in os.environ.items() if not k.startswith("GEMINI_SIDECAR_")}
    if mode is not None:
        env["GEMINI_SIDECAR_READ_GUARD"] = mode
    env.update(extra_env or {})
    proc = subprocess.run([str(HOOK)], input=json.dumps(event) if not isinstance(event, str) else event,
                          capture_output=True, text=True, env=env, timeout=20)
    return proc.returncode, (json.loads(proc.stdout) if proc.stdout.strip() else None)


class ReadGuardTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        d = Path(self.tmp.name)
        self.big = d / "big.py"
        self.big.write_text("x = 1\n" * 1000)
        self.small = d / "small.py"
        self.small.write_text("x = 1\n" * 10)
        staging = d / ".gemini4-staging" / "run"
        staging.mkdir(parents=True)
        self.staged = staging / "big.py"
        self.staged.write_text("x = 1\n" * 1000)

    def tearDown(self):
        self.tmp.cleanup()

    def read(self, path, **kw):
        return {"tool_name": "Read", "tool_input": {"file_path": str(path), **kw}}

    def test_off_by_default(self):
        self.assertEqual(run_hook(self.read(self.big)), (0, None))
        self.assertEqual(run_hook(self.read(self.big), "off"), (0, None))

    def test_block_denies_whole_read_of_large_file(self):
        code, out = run_hook(self.read(self.big), "block")
        self.assertEqual(code, 0)
        self.assertEqual(out["hookSpecificOutput"]["permissionDecision"], "deny")
        self.assertIn("gemini4_analyze_codebase", out["hookSpecificOutput"]["permissionDecisionReason"])

    def test_suggest_allows_with_context(self):
        _, out = run_hook(self.read(self.big), "suggest")
        # Never auto-approve: the normal permission flow must still decide.
        self.assertNotIn("permissionDecision", out["hookSpecificOutput"])
        self.assertIn("offset and limit", out["hookSpecificOutput"]["additionalContext"])

    def test_partial_small_staged_and_missing_reads_pass(self):
        for event in (self.read(self.big, offset=10, limit=20), self.read(self.big, limit=50),
                      self.read(self.small), self.read(self.staged), self.read("/no/such/file.py")):
            with self.subTest(event=event):
                self.assertEqual(run_hook(event, "block"), (0, None))

    def test_threshold_is_configurable(self):
        self.assertEqual(run_hook(self.read(self.big), "block", {"GEMINI_SIDECAR_READ_GUARD_LINES": "5000"}), (0, None))

    def test_bad_input_never_blocks(self):
        self.assertEqual(run_hook("not json", "block"), (0, None))
        self.assertEqual(run_hook({"tool_name": "Bash", "tool_input": {}}, "block"), (0, None))


if __name__ == "__main__":
    unittest.main()
