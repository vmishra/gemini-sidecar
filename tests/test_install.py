"""Installer safety tests. Each runs install.sh with a throwaway HOME."""

import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

KIT = Path(__file__).resolve().parents[1]
INSTALL = KIT / "install.sh"


class InstallerSafetyTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.home = self.tmp / "home"
        self.home.mkdir()
        self.proj = self.tmp / "proj"
        self.proj.mkdir()
        self.env = {k: v for k, v in os.environ.items() if not k.startswith(("GEMINI", "GOOGLE", "ANTHROPIC"))}
        self.env["HOME"] = str(self.home)

    def run_install(self, *args, cwd=None):
        return subprocess.run(["bash", str(INSTALL), *args], cwd=cwd or self.proj, env=self.env,
                              capture_output=True, text=True, timeout=60)

    def test_planted_python_module_in_cwd_is_not_imported(self):
        marker = self.tmp / "PWNED"
        (self.proj / "json.py").write_text(f"open({str(marker)!r}, 'w').write('x')\nfrom json import *\n")
        result = self.run_install("--gateway-profile", "hybrid")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(marker.exists())
        self.assertTrue((self.proj / ".claude" / "settings.local.json").is_file())

    def test_symlinked_settings_target_is_refused(self):
        victim = self.home / ".claude" / "settings.json"
        victim.parent.mkdir()
        victim.write_text('{"model": "mine"}')
        (self.proj / ".claude").mkdir()
        os.symlink(victim, self.proj / ".claude" / "settings.local.json")
        result = self.run_install("--gateway-profile", "all-gemini")
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(json.loads(victim.read_text()), {"model": "mine"})
        self.assertFalse(list((self.proj / ".claude").glob("*.bak.*")))

    def test_existing_settings_are_merged_not_replaced(self):
        (self.proj / ".claude").mkdir()
        (self.proj / ".claude" / "settings.local.json").write_text('{"permissions": {"allow": ["Bash(npm test)"]}}')
        self.assertEqual(self.run_install("--gateway-profile", "hybrid").returncode, 0)
        merged = json.loads((self.proj / ".claude" / "settings.local.json").read_text())
        self.assertEqual(merged["permissions"], {"allow": ["Bash(npm test)"]})
        self.assertIn("ANTHROPIC_BASE_URL", merged["env"])

    def test_codex_entry_in_any_spelling_is_not_duplicated(self):
        codex = self.home / ".codex"
        codex.mkdir()
        for text in ('[mcp_servers."gemini4"]\ncommand = "x"\n', '[mcp_servers]\ngemini4 = { command = "x" }\n'):
            (codex / "config.toml").write_text(text)
            result = self.run_install("--codex")
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual((codex / "config.toml").read_text(), text)

    def test_doctor_never_prints_secret_values(self):
        self.env["GEMINI_API_KEY"] = "AIzaSy-super-secret-value-123"
        result = self.run_install("--doctor", "--json")
        self.assertNotIn("super-secret", result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
