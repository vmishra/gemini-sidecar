"""Offline tests for plugins/gemini/mcp/gemini4_mcp_server.py.

No network access: every Gemini call is replaced with a fake that records the request.
Run from the repository root: python3 -m unittest discover -s tests
"""

from __future__ import annotations

import importlib.util
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

for _var in (
    "GEMINI_API_KEY", "GOOGLE_API_KEY", "GOOGLE_GENAI_USE_VERTEXAI", "GOOGLE_CLOUD_PROJECT",
    "GEMINI4_PLUGIN_API_KEY", "GEMINI4_PLUGIN_USE_VERTEX", "GEMINI4_WORKSPACE_ROOT",
    "CLAUDE_PROJECT_DIR", "GEMINI4_ENABLE_AGY_CLI",
):
    os.environ.pop(_var, None)

SERVER = Path(__file__).resolve().parents[1] / "plugins" / "gemini" / "mcp" / "gemini4_mcp_server.py"
_spec = importlib.util.spec_from_file_location("gemini4_mcp_server", SERVER)
srv = importlib.util.module_from_spec(_spec)
assert _spec.loader is not None
_spec.loader.exec_module(srv)


class FakeResponse(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def gemini_reply(text: str, finish: str = "STOP", usage=None) -> FakeResponse:
    body = {
        "candidates": [{"content": {"parts": [{"text": "thinking...", "thought": True}, {"text": text}]},
                        "finishReason": finish}],
        "usageMetadata": usage or {"promptTokenCount": 1000, "cachedContentTokenCount": 400,
                                   "candidatesTokenCount": 50, "thoughtsTokenCount": 20},
    }
    return FakeResponse(json.dumps(body).encode())


class Workspace(unittest.TestCase):
    """Creates a throwaway git repository and points the server at it."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name).resolve()
        (self.root / "src").mkdir()
        (self.root / "src" / "app.py").write_text("def add(a, b):\n    return a + b\n")
        (self.root / "src" / "config.py").write_text('KEY = "AIzaSyA1234567890abcdefghijklmnopqrstuv"\n')
        (self.root / "src" / ".env").write_text("SECRET=canary-env\n")
        (self.root / "src" / "server.pem").write_text("-----BEGIN PRIVATE KEY-----\nabc\n-----END PRIVATE KEY-----\n")
        (self.root / "src" / "debug.log").write_text("gitignored-canary\n")
        (self.root / ".gitignore").write_text("*.log\n")
        (self.root / "logo.png").write_bytes(b"\x89PNG\r\n\x1a\n\0\0")
        self.outside = Path(tempfile.mkdtemp()).resolve()
        (self.outside / "secret.txt").write_text("outside-canary\n")
        os.symlink(self.outside / "secret.txt", self.root / "src" / "link.txt")
        subprocess.run(["git", "init", "-q"], cwd=self.root, check=True)
        subprocess.run(["git", "add", "-A"], cwd=self.root, check=True)
        subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@example.com", "commit", "-qm", "init"],
                       cwd=self.root, check=True)
        self.env = mock.patch.dict(os.environ, {"GEMINI4_WORKSPACE_ROOT": str(self.root)})
        self.env.start()
        srv.USAGE.clear()

    def tearDown(self):
        self.env.stop()
        self.tmp.cleanup()


class ConfinementTests(Workspace):
    def test_directory_excludes_secrets_symlinks_gitignored_and_binary(self):
        corpus, meta = srv.collect_files(["src/", "logo.png"], self.root)
        self.assertEqual(sorted(meta["files"]), ["src/app.py", "src/config.py"])
        for canary in ("canary-env", "outside-canary", "gitignored-canary", "BEGIN PRIVATE KEY", "AIzaSy"):
            self.assertNotIn(canary, corpus)
        self.assertEqual(meta["redactions"], 1)
        self.assertIn("src/.env", meta["skipped"]["secret_file"])

    def test_explicit_secret_file_is_refused(self):
        with self.assertRaises(srv.ToolError):
            srv.collect_files(["src/.env"], self.root)

    def test_paths_outside_workspace_are_rejected(self):
        for bad in (str(self.outside / "secret.txt"), "../x", "/etc/hosts", "src/../../x"):
            with self.subTest(bad=bad), self.assertRaises(srv.ToolError):
                srv.collect_files([bad], self.root)

    def test_workspace_root_argument_cannot_escape(self):
        with self.assertRaises(srv.ToolError):
            srv.resolve_workspace(str(self.outside))
        self.assertEqual(srv.resolve_workspace("src"), self.root / "src")

    def test_line_numbers_only_when_requested(self):
        numbered, _ = srv.collect_files(["src/app.py"], self.root)
        plain, _ = srv.collect_files(["src/app.py"], self.root, numbered=False)
        self.assertIn("    2|     return a + b", numbered)
        self.assertNotIn("|", plain)

    def test_staging_refuses_traversal_and_incomplete_files(self):
        text = (
            "<<<FILE ../evil.py>>>\nx\n<<<END FILE>>>\n"
            "<<<FILE /abs.py>>>\nx\n<<<END FILE>>>\n"
            "<<<FILE src/new.py>>>\nprint(1)\n<<<END FILE>>>\n"
            "## Notes\nok\n"
            "<<<FILE src/cut.py>>>\nunfinished"
        )
        stage, written, refused, notes = srv.stage_generated_files(text, self.root, truncated=True)
        self.assertEqual(written, ["src/new.py"])
        self.assertEqual(len(refused), 3)
        self.assertFalse((self.root.parent / "evil.py").exists())
        self.assertTrue((stage / "src" / "new.py").is_file())
        self.assertEqual((self.root / ".gemini4-staging" / ".gitignore").read_text(), "*\n")


class ReviewRegressionTests(Workspace):
    """Exploits found in an independent review; each must stay fixed."""

    def test_staged_output_cannot_create_git_metadata(self):
        text = ("<<<FILE .git/config>>>\n[core]\n\tfsmonitor = touch PWNED\n<<<END FILE>>>\n"
                "<<<FILE sub/.GIT/HEAD>>>\nref: x\n<<<END FILE>>>\n"
                "<<<FILE .gemini4-staging/x>>>\ny\n<<<END FILE>>>\n"
                "<<<FILE ok.py>>>\nz\n<<<END FILE>>>\n")
        stage, written, refused, _ = srv.stage_generated_files(text, self.root, truncated=False)
        self.assertEqual(written, ["ok.py"])
        self.assertEqual(len(refused), 3)
        self.assertFalse((stage / ".git").exists())

    def test_symlinked_staging_dir_is_refused(self):
        os.symlink(self.outside, self.root / ".gemini4-staging")
        with self.assertRaises(srv.ToolError):
            srv.stage_generated_files("<<<FILE a.py>>>\nx\n<<<END FILE>>>", self.root, truncated=False)
        self.assertFalse((self.outside / "a.py").exists())
        self.assertFalse((self.outside / ".gitignore").exists())

    def test_two_runs_in_same_second_do_not_collide(self):
        a = srv.stage_generated_files("<<<FILE a.py>>>\n1\n<<<END FILE>>>", self.root, False)[0]
        b = srv.stage_generated_files("<<<FILE a.py>>>\n2\n<<<END FILE>>>", self.root, False)[0]
        self.assertNotEqual(a, b)

    def test_git_directory_never_read(self):
        with self.assertRaises(srv.ToolError):
            srv.collect_files([".git/config"], self.root)

    def test_more_secret_names(self):
        for name in (".pgpass", ".htpasswd", "secret.yaml", "key.asc", "Secrets.PEM", ".ENV"):
            self.assertTrue(srv.is_secret_file(Path(name)), name)
        self.assertFalse(srv.is_secret_file(Path(".env.example")))

    def test_pathspec_magic_filename_does_not_leak_excluded_secret(self):
        subprocess.run(["git", "add", "-f", "src/.env"], cwd=self.root, check=True)
        (self.root / "*").write_text("star\n")
        subprocess.run(["git", "add", "*"], cwd=self.root, check=True, env={**os.environ, "GIT_LITERAL_PATHSPECS": "1"})
        subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@example.com", "commit", "-qm", "x"],
                       cwd=self.root, check=True)
        (self.root / "src" / ".env").write_text("SECRET=hunter3\n")
        (self.root / "*").write_text("star changed\n")
        with mock.patch.dict(os.environ, {"GEMINI_API_KEY": "k"}), \
             mock.patch.object(srv.urllib.request, "urlopen", return_value=gemini_reply("ok")) as op:
            res = srv.execute_tool("gemini4_review_diff", {"base": "HEAD", "include_full_files": False})
        sent = json.loads(op.call_args[0][0].data)["contents"][0]["parts"][0]["text"]
        self.assertNotIn("hunter3", sent)
        self.assertIn("star changed", sent)
        self.assertIn("excluded secret files", res)

    def test_quote_in_filename_cannot_break_delimiter(self):
        (self.root / 'a">b.py').write_text("x = 1\n")
        corpus, _ = srv.collect_files(['a">b.py'], self.root)
        self.assertIn('<file path="a\\">b.py">', corpus)

    def test_large_log_keeps_tail(self):
        (self.root / "big.log").write_text("noise\n" * 300_000 + "FAILED test_tail\n")
        tail = srv.read_log_tail("big.log", self.root, 10_000)
        self.assertIn("FAILED test_tail", tail)
        self.assertIn("log head omitted", tail)

    def test_home_or_filesystem_root_refused_as_workspace(self):
        for bad in (str(Path.home()), "/"):
            with mock.patch.dict(os.environ, {"GEMINI4_WORKSPACE_ROOT": bad}), self.assertRaises(srv.ToolError):
                srv.workspace_root()

    def test_agy_only_sees_filtered_copy(self):
        captured = {}

        def fake_run(cmd, cwd, **kw):
            captured["cwd"] = cwd
            captured["files"] = sorted(str(p.relative_to(cwd)) for p in Path(cwd).rglob("*") if p.is_file())
            captured["config"] = (Path(cwd) / "src" / "config.py").read_text()
            return subprocess.CompletedProcess(cmd, 0, stdout="critique", stderr="")

        _, meta = srv.collect_files(["src/"], self.root)
        with mock.patch.dict(os.environ, {"GEMINI4_ENABLE_AGY_CLI": "1"}), \
             mock.patch.object(srv, "find_agy", return_value="/bin/agy"), \
             mock.patch.object(srv.subprocess, "run", side_effect=fake_run):
            res, reason = srv.run_agy_plan("q", meta["files"], self.root, "gemini-3.8-flash", "low")
        self.assertEqual(res["text"], "critique")
        self.assertNotEqual(Path(captured["cwd"]).resolve(), self.root)
        self.assertEqual(captured["files"], ["src/app.py", "src/config.py"])
        self.assertNotIn("AIzaSy", captured["config"])


class GeminiCallTests(Workspace):
    def call(self, name, args, reply=None):
        with mock.patch.dict(os.environ, {"GEMINI_API_KEY": "test-key"}), \
             mock.patch.object(srv.urllib.request, "urlopen", return_value=reply or gemini_reply("answer")) as op:
            res = srv.handle_request({"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                                      "params": {"name": name, "arguments": args}})["result"]
        return res, op

    def test_api_key_sent_in_header_not_url(self):
        res, op = self.call("gemini4_analyze_codebase", {"question": "q", "paths": ["src/"]})
        self.assertFalse(res["isError"])
        req = op.call_args[0][0]
        self.assertNotIn("test-key", req.full_url)
        self.assertEqual(req.get_header("X-goog-api-key"), "test-key")
        self.assertIn("gemini-3.8-flash", req.full_url)

    def test_thought_parts_dropped_and_usage_reported(self):
        res, _ = self.call("gemini4_analyze_codebase", {"question": "q", "paths": ["src/"], "model_tier": "pro"})
        text = res["content"][0]["text"]
        self.assertTrue(text.startswith("answer"))
        self.assertNotIn("thinking...", text)
        self.assertIn("1,000 tok (400 cached)", text)
        self.assertIn("gemini-4-argon", text)
        status = srv.tool_status()
        self.assertIn("| `gemini-4-argon` | 1 | 1,000 | 400 | 70 |", status)

    def test_cost_uses_cached_rate(self):
        usage = {"promptTokenCount": 1_000_000, "cachedContentTokenCount": 1_000_000, "candidatesTokenCount": 0}
        self.assertAlmostEqual(srv.estimate_cost("gemini-3.8-flash", usage), 0.075)

    def test_no_credentials_is_an_error(self):
        res = srv.handle_request({"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {
            "name": "gemini4_security_audit", "arguments": {"paths": ["src/"]}}})["result"]
        self.assertTrue(res["isError"])
        self.assertIn("No Gemini credentials", res["content"][0]["text"])

    def test_http_error_is_reported_without_key(self):
        err = srv.urllib.error.HTTPError("https://x", 403, "Forbidden", {},
                                         io.BytesIO(b'{"error": {"message": "denied"}}'))
        with mock.patch.dict(os.environ, {"GEMINI_API_KEY": "test-key"}), \
             mock.patch.object(srv.urllib.request, "urlopen", side_effect=err):
            res = srv.handle_request({"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {
                "name": "gemini4_analyze_codebase", "arguments": {"question": "q", "paths": ["src/"]}}})["result"]
        self.assertTrue(res["isError"])
        self.assertIn("HTTP 403", res["content"][0]["text"])
        self.assertNotIn("test-key", res["content"][0]["text"])

    def test_review_diff_excludes_secret_files(self):
        (self.root / "src" / "app.py").write_text("def add(a, b):\n    return a - b\n")
        subprocess.run(["git", "add", "-f", "src/.env"], cwd=self.root, check=True)
        (self.root / "src" / ".env").write_text("SECRET=changed\n")
        res, op = self.call("gemini4_review_diff", {"base": "HEAD"})
        self.assertFalse(res["isError"])
        sent = json.loads(op.call_args[0][0].data)["contents"][0]["parts"][0]["text"]
        self.assertIn("return a - b", sent)
        self.assertNotIn("SECRET=", sent)

    def test_review_diff_rejects_option_like_ref(self):
        res, _ = self.call("gemini4_review_diff", {"base": "--output=/tmp/x"})
        self.assertTrue(res["isError"])

    def test_refactor_stages_files(self):
        reply = gemini_reply("<<<FILE src/app.py>>>\ndef add(a, b):\n    return b + a\n<<<END FILE>>>\n## Notes\nswap")
        res, _ = self.call("gemini4_long_decode_refactor", {"spec": "swap", "paths": ["src/app.py"]}, reply)
        self.assertFalse(res["isError"])
        self.assertIn("`src/app.py` (modified, +1 -1 lines)", res["content"][0]["text"])
        self.assertEqual((self.root / "src" / "app.py").read_text(), "def add(a, b):\n    return a + b\n")

    def test_triage_reads_log_inside_workspace(self):
        (self.root / ".gemini4-staging").mkdir()
        (self.root / ".gemini4-staging" / "test-output.log").write_text("FAILED test_add\n")
        res, op = self.call("gemini4_triage_failures", {"log_path": ".gemini4-staging/test-output.log",
                                                         "paths": ["src/app.py"]})
        self.assertFalse(res["isError"])
        self.assertIn("FAILED test_add", json.loads(op.call_args[0][0].data)["contents"][0]["parts"][0]["text"])

    def test_vertex_flag_from_env_not_overridden_by_plugin_default(self):
        with mock.patch.dict(os.environ, {"GEMINI4_PLUGIN_USE_VERTEX": "false", "GOOGLE_GENAI_USE_VERTEXAI": "true"}):
            self.assertTrue(srv.resolve_credentials()["use_vertex"])


class ProtocolTests(unittest.TestCase):
    def test_stdio_handshake_and_tool_list(self):
        msgs = [
            {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2025-06-18"}},
            {"jsonrpc": "2.0", "method": "notifications/initialized"},
            {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
            {"jsonrpc": "2.0", "id": 3, "method": "bogus"},
        ]
        proc = subprocess.run([sys.executable, str(SERVER)], input="\n".join(json.dumps(m) for m in msgs) + "\n",
                              capture_output=True, text=True, timeout=30)
        replies = [json.loads(line) for line in proc.stdout.splitlines() if line.strip()]
        self.assertEqual([r["id"] for r in replies], [1, 2, 3])
        self.assertEqual(replies[0]["result"]["protocolVersion"], "2025-06-18")
        names = {t["name"] for t in replies[1]["result"]["tools"]}
        self.assertEqual(names, {
            "gemini4_analyze_codebase", "gemini4_security_audit", "gemini4_review_diff",
            "gemini4_long_decode_refactor", "gemini4_triage_failures", "ask_antigravity", "gemini4_status",
        })
        self.assertEqual(replies[2]["error"]["code"], -32601)

    def test_model_id_normalization(self):
        self.assertEqual(srv.normalize_model_id("claude-gemini-3.8-flash[1m]"), "gemini-3.8-flash")
        self.assertEqual(srv.normalize_model_id("gemini/gemini-4-argon"), "gemini-4-argon")
        self.assertEqual(srv.normalize_model_id("gemini-3.8-flash[effort=low]"), "gemini-3.8-flash")


if __name__ == "__main__":
    unittest.main()
