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
        tail, desc = srv.read_log_digest("big.log", self.root, 10_000)
        self.assertIn("FAILED test_tail", tail)
        self.assertIn("omitted", tail)
        self.assertIn("kept", desc)

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


class SelfAuditRegressionTests(Workspace):
    """Findings from running /gemini:security-audit on this repository."""

    def test_glob_respects_gitignore_and_hidden(self):
        corpus, meta = srv.collect_files(["src/*"], self.root)
        self.assertNotIn("gitignored-canary", corpus)
        self.assertNotIn("src/debug.log", meta["files"])
        self.assertNotIn("canary-env", corpus)

    def test_renamed_secret_is_excluded_from_review(self):
        # src/.env is committed by the fixture.
        subprocess.run(["git", "mv", "src/.env", "src/.env.example"], cwd=self.root, check=True)
        (self.root / "src" / "app.py").write_text("def add(a, b):\n    return a * b\n")
        with mock.patch.dict(os.environ, {"GEMINI_API_KEY": "k"}), \
             mock.patch.object(srv.urllib.request, "urlopen", return_value=gemini_reply("ok")) as op:
            srv.execute_tool("gemini4_review_diff", {"base": "HEAD", "include_full_files": False})
        sent = json.loads(op.call_args[0][0].data)["contents"][0]["parts"][0]["text"]
        self.assertNotIn("canary-env", sent)

    def test_review_is_limited_to_workspace_subdirectory(self):
        (self.root / "other").mkdir()
        (self.root / "other" / "x.py").write_text("sibling = 1\n")
        subprocess.run(["git", "add", "other"], cwd=self.root, check=True)
        subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@example.com", "commit", "-qm", "o"],
                       cwd=self.root, check=True)
        (self.root / "other" / "x.py").write_text("sibling = 2\n")
        (self.root / "src" / "app.py").write_text("def add(a, b):\n    return 0\n")
        with mock.patch.dict(os.environ, {"GEMINI_API_KEY": "k"}), \
             mock.patch.object(srv.urllib.request, "urlopen", return_value=gemini_reply("ok")) as op:
            srv.execute_tool("gemini4_review_diff", {"base": "HEAD", "include_full_files": False, "workspace_root": "src"})
        sent = json.loads(op.call_args[0][0].data)["contents"][0]["parts"][0]["text"]
        self.assertIn("return 0", sent)
        self.assertNotIn("sibling", sent)

    def test_url_credentials_are_redacted(self):
        text, n = srv.redact_secrets("db = 'postgres://admin:s3cr3t@db.internal:5432/app'\nurl = https://example.com/path")
        self.assertNotIn("s3cr3t", text)
        self.assertIn("postgres://[REDACTED:url-credentials]@db.internal:5432/app", text)
        self.assertIn("https://example.com/path", text)
        self.assertEqual(n, 1)

    def test_private_key_regex_is_bounded(self):
        import time as _t
        start = _t.time()
        srv.redact_secrets("-----BEGIN RSA PRIVATE KEY-----\n" * 5000)
        self.assertLess(_t.time() - start, 2.0)

    def test_staging_rejects_dot_and_secret_names(self):
        _, written, refused, _ = srv.stage_generated_files(
            "<<<FILE .>>>\nx\n<<<END FILE>>>\n<<<FILE .env>>>\nK=1\n<<<END FILE>>>\n<<<FILE a.py>>>\n1\n<<<END FILE>>>",
            self.root, False)
        self.assertEqual(written, ["a.py"])
        self.assertEqual(len(refused), 2)

    def test_agy_environment_is_scrubbed(self):
        with mock.patch.dict(os.environ, {"CLAUDE_PROJECT_DIR": "/x", "GITHUB_TOKEN": "t", "GEMINI_API_KEY": "g"}):
            env = srv._agy_env()
        self.assertNotIn("CLAUDE_PROJECT_DIR", env)
        self.assertNotIn("GITHUB_TOKEN", env)
        self.assertNotIn("GEMINI4_WORKSPACE_ROOT", env)
        self.assertEqual(env["GEMINI_API_KEY"], "g")


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

    def test_vertex_location_cannot_change_host(self):
        env = {"GOOGLE_GENAI_USE_VERTEXAI": "true", "GOOGLE_CLOUD_PROJECT": "my-project",
               "GOOGLE_CLOUD_LOCATION": "evil.example.com/x#"}
        with mock.patch.dict(os.environ, env), mock.patch.object(srv, "_vertex_token", return_value="tok"), \
             mock.patch.object(srv.urllib.request, "urlopen") as op:
            with self.assertRaises(srv.ToolError):
                srv.call_gemini("gemini-3.8-flash", "s", "p")
        op.assert_not_called()

    def test_vertex_flag_from_env_not_overridden_by_plugin_default(self):
        with mock.patch.dict(os.environ, {"GEMINI4_PLUGIN_USE_VERTEX": "false", "GOOGLE_GENAI_USE_VERTEXAI": "true"}):
            self.assertTrue(srv.resolve_credentials()["use_vertex"])


def grounded_reply(text: str) -> FakeResponse:
    body = {
        "candidates": [{"content": {"parts": [{"text": text}]}, "finishReason": "STOP",
                        "groundingMetadata": {"webSearchQueries": ["requests cve"],
                                              "groundingChunks": [{"web": {"uri": "https://example.org/a", "title": "example.org"}},
                                                                  {"web": {"uri": "https://example.org/a", "title": "dup"}}]}}],
        "usageMetadata": {"promptTokenCount": 10, "candidatesTokenCount": 5},
    }
    return FakeResponse(json.dumps(body).encode())


class GeminiStrengthToolTests(Workspace):
    def call(self, name, args, reply=None):
        with mock.patch.dict(os.environ, {"GEMINI_API_KEY": "k"}), \
             mock.patch.object(srv.urllib.request, "urlopen", return_value=reply or gemini_reply("ok")) as op:
            res = srv.handle_request({"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                                      "params": {"name": name, "arguments": args}})["result"]
        body = json.loads(op.call_args[0][0].data) if op.called else None
        return res, body

    def test_deps_autodetects_manifests_and_uses_search_grounding(self):
        (self.root / "requirements.txt").write_text("requests==2.25.0\nflask[async]>=1.1,<2  # web\n")
        (self.root / "web").mkdir()
        (self.root / "web" / "package.json").write_text('{"dependencies": {"lodash": "^4.17.0"}}')
        res, body = self.call("gemini4_check_dependencies", {}, grounded_reply("table"))
        self.assertFalse(res["isError"])
        self.assertEqual(body["tools"], [{"googleSearch": {}}])
        prompt = body["contents"][0]["parts"][-1]["text"]
        self.assertIn("- requests ==2.25.0  (requirements.txt)", prompt)
        self.assertIn("- flask >=1.1,<2  (requirements.txt)", prompt)
        self.assertIn("- lodash ^4.17.0  (web/package.json)", prompt)
        text = res["content"][0]["text"]
        self.assertIn("**Sources**", text)
        self.assertEqual(text.count("https://example.org/a"), 1)

    def test_deps_never_forwards_credentials_in_url_versions(self):
        (self.root / "package.json").write_text(json.dumps({"dependencies": {
            "private-lib": "git+https://bot:ghp_abcdefghijklmnopqrstuvwxyz0123456789@github.com/acme/lib.git",
            "other": "https://user:hunter2@registry.example.com/other.tgz",
            "lodash": "^4.17.21"}}))
        res, body = self.call("gemini4_check_dependencies", {"paths": ["package.json"]}, grounded_reply("t"))
        prompt = body["contents"][0]["parts"][-1]["text"]
        self.assertNotIn("hunter2", prompt)
        self.assertNotIn("ghp_abcdefghijklmnopqrstuvwxyz0123456789", prompt)
        self.assertIn("- private-lib <url or path>  (package.json)", prompt)
        self.assertIn("- lodash ^4.17.21  (package.json)", prompt)

    def test_deps_without_manifests_is_an_error(self):
        res, _ = self.call("gemini4_check_dependencies", {})
        self.assertTrue(res["isError"])

    def test_spec_check_sends_pdf_inline(self):
        (self.root / "spec.pdf").write_bytes(b"%PDF-1.4 fake")
        res, body = self.call("gemini4_spec_check", {"spec": "spec.pdf", "paths": ["src/app.py"]})
        self.assertFalse(res["isError"])
        part = body["contents"][0]["parts"][0]["inlineData"]
        self.assertEqual(part["mimeType"], "application/pdf")
        self.assertNotIn("tools", body)

    def test_spec_check_url_uses_url_context(self):
        res, body = self.call("gemini4_spec_check", {"spec": "https://www.rfc-editor.org/rfc/rfc6585", "paths": ["src/"]})
        self.assertFalse(res["isError"])
        self.assertEqual(body["tools"], [{"urlContext": {}}])
        self.assertIn("rfc6585", body["contents"][0]["parts"][-1]["text"])

    def test_spec_check_text_spec_is_read_as_text(self):
        (self.root / "SPEC.md").write_text("The API MUST return 429.\n")
        res, body = self.call("gemini4_spec_check", {"spec": "SPEC.md", "paths": ["src/app.py"]})
        self.assertFalse(res["isError"])
        self.assertIn("MUST return 429", body["contents"][0]["parts"][-1]["text"])

    def test_visual_debug_sends_image_and_video(self):
        (self.root / "shot.png").write_bytes(b"\x89PNG\r\n\x1a\nfake")
        (self.root / "rec.mov").write_bytes(b"fake-mov")
        res, body = self.call("gemini4_visual_debug", {"media": ["shot.png", "rec.mov"], "question": "why?", "paths": ["src/"]})
        self.assertFalse(res["isError"])
        mimes = [p["inlineData"]["mimeType"] for p in body["contents"][0]["parts"] if "inlineData" in p]
        self.assertEqual(mimes, ["image/png", "video/quicktime"])

    def test_media_confinement_type_and_size(self):
        (self.root / "notes.txt").write_text("x")
        for media in (["../x.png"], [str(self.outside / "secret.txt")], ["notes.txt"], ["missing.png"]):
            with self.subTest(media=media):
                res, _ = self.call("gemini4_visual_debug", {"media": media, "question": "q"})
                self.assertTrue(res["isError"])
        (self.root / "big.mp4").write_bytes(b"0" * 2000)
        with mock.patch.object(srv, "MAX_MEDIA_BYTES", 1000):
            res, _ = self.call("gemini4_visual_debug", {"media": ["big.mp4"], "question": "q"})
        self.assertTrue(res["isError"])
        self.assertIn("limit per call", res["content"][0]["text"])

    def test_architecture_mode_stages_document(self):
        reply = gemini_reply("<<<FILE ARCHITECTURE.md>>>\n# Architecture\n<<<END FILE>>>\n## Notes\nok")
        res, body = self.call("gemini4_long_decode_refactor", {"spec": "guide", "paths": ["."], "mode": "architecture"}, reply)
        self.assertFalse(res["isError"])
        self.assertIn("ARCHITECTURE.md", res["content"][0]["text"])
        self.assertIn("Write ARCHITECTURE.md", body["contents"][0]["parts"][-1]["text"])


class ContextEfficiencyTests(Workspace):
    def test_estimate_only_makes_no_api_call(self):
        with mock.patch.object(srv.urllib.request, "urlopen") as op:
            for name, args in (("gemini4_analyze_codebase", {"question": "q", "paths": ["src/"]}),
                               ("gemini4_security_audit", {"paths": ["src/"]}),
                               ("gemini4_long_decode_refactor", {"spec": "s", "paths": ["src/"]}),
                               ("gemini4_spec_check", {"spec": "https://example.com/spec", "paths": ["src/"]})):
                text = srv.execute_tool(name, {**args, "estimate_only": True})
                self.assertIn("Gemini was not called", text)
                self.assertIn("Estimated cost", text)
        op.assert_not_called()

    def test_log_digest_keeps_evidence_from_middle_of_log(self):
        lines = [f"ok line {i}" for i in range(20_000)]
        lines[14_238] = "FAILED tests/test_pay.py::test_refund - AssertionError: 0 != 45"
        (self.root / "huge.log").write_text("\n".join(lines) + "\n")
        corpus, desc = srv.read_log_digest("huge.log", self.root, 20_000)
        self.assertIn("test_refund - AssertionError", corpus)
        self.assertIn("ok line 19999", corpus)
        self.assertIn("lines 1-", corpus)  # dropped ranges are declared in place
        self.assertLess(len(corpus), 25_000)
        self.assertIn("kept", desc)

    def test_small_log_is_sent_whole(self):
        (self.root / "small.log").write_text("a\nb\nFAILED x\n")
        corpus, desc = srv.read_log_digest("small.log", self.root, 20_000)
        self.assertIn("all 3 lines", desc)

    def test_omitted_files_are_named(self):
        for i in range(5):
            (self.root / "src" / f"m{i}.py").write_text("x = 1\n" * 200)
        _, meta = srv.collect_files(["src/"], self.root, max_chars=2_500)
        self.assertTrue(meta["truncated"])
        self.assertTrue(meta["omitted"])
        self.assertIn(meta["omitted"][0], srv.describe_scope(meta))

    def test_tool_schema_footprint_budget(self):
        # Tool schemas are loaded into the agent's context by some hosts on every turn.
        size = len(json.dumps(srv.TOOLS))
        self.assertLess(size, 8_500, f"tool schemas grew to {size} bytes; trim descriptions")


class PreReleaseSecurityTests(Workspace):
    """Findings from the pre-release adversarial review; each reproduces the original attack."""

    def test_repo_git_config_cannot_run_commands(self):
        marker = self.root.parent / f"pwn-{self.root.name}"
        for key, cmd in (("core.fsmonitor", f"touch {marker}-fsmonitor; false"),
                         ("diff.external", f"sh -c 'touch {marker}-external'"),
                         ("core.pager", f"touch {marker}-pager"),
                         ("filter.evil.clean", f"sh -c 'touch {marker}-filter; cat'")):
            subprocess.run(["git", "config", key, cmd], cwd=self.root, check=True)
        (self.root / ".gitattributes").write_text("*.py filter=evil diff=evil\n")
        (self.root / "src" / "app.py").write_text("def add(a, b):\n    return a - b\n")
        with mock.patch.dict(os.environ, {"GEMINI_API_KEY": "k"}), \
             mock.patch.object(srv.urllib.request, "urlopen", return_value=gemini_reply("ok")) as op:
            srv.execute_tool("gemini4_review_diff", {"base": "HEAD"})
            srv.collect_files(["."], self.root)
        sent = json.loads(op.call_args[0][0].data)["contents"][0]["parts"][0]["text"]
        self.assertIn("return a - b", sent)
        self.assertEqual([p.name for p in self.root.parent.glob(f"pwn-{self.root.name}*")], [])

    def test_gitattributes_cannot_hide_a_change(self):
        (self.root / ".gitattributes").write_text("app.py -diff\n")
        subprocess.run(["git", "add", ".gitattributes"], cwd=self.root, check=True)
        subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@example.com", "commit", "-qm", "a"],
                       cwd=self.root, check=True)
        (self.root / "src" / "app.py").write_text("def add(a, b):\n    return backdoor()\n")
        with mock.patch.dict(os.environ, {"GEMINI_API_KEY": "k"}), \
             mock.patch.object(srv.urllib.request, "urlopen", return_value=gemini_reply("ok")) as op:
            srv.execute_tool("gemini4_review_diff", {"base": "HEAD", "include_full_files": False})
        self.assertIn("return backdoor()", json.loads(op.call_args[0][0].data)["contents"][0]["parts"][0]["text"])

    def test_changed_binary_files_are_listed_not_diffed(self):
        # logo.png is committed by the fixture.
        (self.root / "logo.png").write_bytes(b"\x89PNG\r\n\x1a\n\xf3\xff\x00\x01binary")
        (self.root / "src" / "app.py").write_text("def add(a, b):\n    return a - b\n")
        with mock.patch.dict(os.environ, {"GEMINI_API_KEY": "k"}), \
             mock.patch.object(srv.urllib.request, "urlopen", return_value=gemini_reply("ok")) as op:
            text = srv.execute_tool("gemini4_review_diff", {"base": "HEAD"})
        sent = json.loads(op.call_args[0][0].data)["contents"][0]["parts"][0]["text"]
        self.assertIn("return a - b", sent)
        self.assertNotIn("\\xf3", sent)
        self.assertIn("binary files changed, not reviewed: logo.png", text)

    def test_nul_byte_cannot_hide_a_text_change(self):
        (self.root / "src" / "app.py").write_bytes(b"def add(a, b):\n    return backdoor()  \x00\n")
        with mock.patch.dict(os.environ, {"GEMINI_API_KEY": "k"}), \
             mock.patch.object(srv.urllib.request, "urlopen", return_value=gemini_reply("ok")) as op:
            text = srv.execute_tool("gemini4_review_diff", {"base": "HEAD", "include_full_files": False})
        self.assertIn("backdoor()", json.loads(op.call_args[0][0].data)["contents"][0]["parts"][0]["text"])
        self.assertIn("NUL bytes", text)

    def test_secret_assignment_regex_is_bounded(self):
        import time as _t
        start = _t.time()
        for text in ("a_" * 100_000 + "password", ("password_token_secret_" * 20_000), "token" * 100_000,
                     "export " + "A" * 100_000 + "_TOKEN=" + "v" * 100_000, "token:" * 100_000):
            srv.redact_secrets(text)
        self.assertLess(_t.time() - start, 3.0)

    def test_base64_padded_and_hyphenated_secrets_are_redacted(self):
        for text, secret in (("SECRET_KEY=dGhpcyBpcyBhIHNlY3JldA==", "dGhpcyBpcyBhIHNlY3JldA=="),
                             ('api-key: "abcdef123456"', "abcdef123456"),
                             ("X-Api-Key: abcdef1234567890", "abcdef1234567890")):
            self.assertNotIn(secret, srv.redact_secrets(text)[0], text)

    def test_assignment_scan_is_linear(self):
        import time as _t
        start = _t.time()
        for text in ("token=" * 200_000, "password='x " * 60_000, "password=" * 50_000 + '"'):
            srv.redact_secrets(text)
        self.assertLess(_t.time() - start, 3.0)

    def test_quotes_and_shared_lines_do_not_hide_secrets(self):
        for text, secret in (('token_type=Bearer,api_key="abcdef123456"', "abcdef123456"),
                             ('token=api_key="secretvalue1"', "secretvalue1"),
                             ('password = "it\'s-a-secret-99"', "it's-a-secret-99"),
                             ("password = 'say\"hi\"secret'", 'say"hi"secret')):
            self.assertNotIn(secret, srv.redact_secrets(text)[0], text)

    def test_fast_assignment_scan_matches_simple_reference(self):
        """The skip-ahead optimisations must never change what is redacted."""
        import random

        def reference(text):
            out, pos, n = [], 0, len(text)
            for m in srv._ASSIGN_RE.finditer(text):
                if m.start() < pos or not srv._SECRET_NAME_RE.search(m.group(1)):
                    continue
                i = m.end()
                if i < n and text[i] in "\"'":
                    j = srv._QUOTED_VALUE_RE[text[i]].match(text, i + 1).end()
                    if j < n and text[j] == text[i] and j - (i + 1) >= 6:
                        out += [text[pos:i + 1], "[REDACTED:secret-assignment]"]
                        pos = j
                    continue
                j = srv._BARE_VALUE_RE.match(text, i).end()
                if j - i >= 6 and srv._LINE_REST_RE.match(text, j):
                    out += [text[pos:i], "[REDACTED:secret-assignment]"]
                    pos = j
            out.append(text[pos:])
            return "".join(out)

        pieces = ["token", "api_key", "password", "x", "abcdef", "123456", "=", ":", " ", '"', "'", ",", "\n",
                  "==", "-", "_", "(", ")", "#", "secret", "Bearer"]
        rng = random.Random(1234)
        for _ in range(4000):
            text = "".join(rng.choice(pieces) for _ in range(rng.randint(1, 40)))
            self.assertEqual(srv._redact_secret_assignments(text)[0], reference(text), repr(text))

    def test_long_values_and_long_name_prefixes_are_still_redacted(self):
        for text in ("API_TOKEN=" + "v" * 2_000, "X" * 200 + "_PASSWORD=hunter2secret",
                     "X" * 200 + '_secret = "abcdefgh123"', 'password = "' + "v" * 2_000 + '"'):
            out, n = srv.redact_secrets(text)
            self.assertEqual(n, 1, text[:40])
            self.assertNotIn("v" * 50, out)
            self.assertNotIn("hunter2secret", out)

    def test_gitignored_files_skipped_even_when_named(self):
        (self.root / "local_settings.py").write_text("DB = 'prod'\n")
        (self.root / ".gitignore").write_text("*.log\nlocal_settings.py\n")
        with self.assertRaises(srv.ToolError):
            srv.collect_files(["local_settings.py"], self.root)
        with mock.patch.dict(os.environ, {"GEMINI4_INCLUDE_IGNORED": "1"}):
            _, meta = srv.collect_files(["local_settings.py"], self.root)
        self.assertEqual(meta["files"], ["local_settings.py"])

    def test_secret_dirs_and_embedded_repos_are_never_read(self):
        for rel in (".docker/config.json", ".aws/config", ".kube/config", "client_secret_123.json", "token.json"):
            path = self.root / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("secret-material\n")
        bare = self.root / "vendor_repo"
        subprocess.run(["git", "init", "-q", "--bare", str(bare)], check=True)
        corpus, meta = srv.collect_files(["."], self.root, numbered=False)
        self.assertNotIn("secret-material", corpus)
        self.assertFalse([f for f in meta["files"] if f.startswith("vendor_repo/")])

    def test_more_token_formats_are_redacted(self):
        samples = ["aws_secret_access_key = wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY",
                   "glpat-abcdefghijklmnopqrstuvwx", "npm_" + "a" * 36, "hf_" + "b" * 34, "sk_test_" + "c" * 24,
                   "GOCSPX-" + "d" * 28, "1//0" + "e" * 30, 'DATABASE_PASSWORD="hunter2hunter2"',
                   "postgres://admin:p@ss/w0rd@db.internal:5432/app",
                   "-----BEGIN PGP PRIVATE KEY BLOCK-----\nabc\n-----END PGP PRIVATE KEY BLOCK-----"]
        for sample in samples:
            out, n = srv.redact_secrets(sample)
            self.assertGreater(n, 0, sample)
        for keep in ('token = request.headers.get("Authorization")', "https://registry.npmjs.org/@scope/pkg"):
            self.assertEqual(srv.redact_secrets(keep)[0], keep)

    def test_typed_secrets_are_redacted_from_prompts(self):
        with mock.patch.dict(os.environ, {"GEMINI_API_KEY": "k"}), \
             mock.patch.object(srv.urllib.request, "urlopen", return_value=gemini_reply("ok")) as op:
            srv.execute_tool("gemini4_analyze_codebase",
                             {"question": "is sk-ant-" + "x" * 30 + " valid?", "paths": ["src/app.py"]})
        self.assertNotIn("sk-ant-" + "x" * 30, json.loads(op.call_args[0][0].data)["contents"][0]["parts"][-1]["text"])

    def test_long_lines_do_not_hang_scanning(self):
        import time as _t
        (self.root / "long.log").write_text(("at " + "x" * 300_000 + "\n") * 3 + "FAILED test_x\n")
        start = _t.time()
        srv.read_log_digest("long.log", self.root, 50_000)
        srv.redact_secrets("-----BEGIN RSA PRIVATE KEY-----\n" * 50_000)
        self.assertLess(_t.time() - start, 3.0)

    def test_spec_url_with_credentials_is_refused(self):
        with self.assertRaises(srv.ToolError):
            srv.execute_tool("gemini4_spec_check", {"spec": "https://user:pw@example.com/spec", "paths": ["src/"]})

    def test_staging_survives_conflicts_and_flags_sensitive_targets(self):
        reply = gemini_reply("<<<FILE a>>>\n1\n<<<END FILE>>>\n<<<FILE a/b>>>\n2\n<<<END FILE>>>\n"
                             "<<<FILE " + "n" * 300 + ".py>>>\n3\n<<<END FILE>>>\n"
                             "<<<FILE .github/workflows/ci.yml>>>\nx\n<<<END FILE>>>\n## Notes\nok")
        with mock.patch.dict(os.environ, {"GEMINI_API_KEY": "k"}), \
             mock.patch.object(srv.urllib.request, "urlopen", return_value=reply):
            text = srv.execute_tool("gemini4_long_decode_refactor", {"spec": "s", "paths": ["src/app.py"]})
        self.assertIn("WARNING", text)
        self.assertIn(".github/workflows/ci.yml", text)
        self.assertIn("Not staged", text)

    def test_malformed_rpc_messages_do_not_kill_the_server(self):
        msgs = ['{"jsonrpc":"2.0","id":1,"method":"tools/call","params":[1]}', "[" * 50_000,
                "Content-Length: -5", '{"jsonrpc":"2.0","id":2,"method":"ping"}']
        proc = subprocess.run([sys.executable, str(SERVER)], input="\n".join(msgs) + "\n",
                              capture_output=True, text=True, timeout=30)
        replies = [json.loads(line) for line in proc.stdout.splitlines() if line.strip()]
        self.assertIn(2, [r.get("id") for r in replies])


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
            "gemini4_check_dependencies", "gemini4_spec_check", "gemini4_visual_debug",
        })
        self.assertEqual(replies[2]["error"]["code"], -32601)

    def test_model_id_normalization(self):
        self.assertEqual(srv.normalize_model_id("claude-gemini-3.8-flash[1m]"), "gemini-3.8-flash")
        self.assertEqual(srv.normalize_model_id("gemini/gemini-4-argon"), "gemini-4-argon")
        self.assertEqual(srv.normalize_model_id("gemini-3.8-flash[effort=low]"), "gemini-3.8-flash")


class ContextBudgetTests(Workspace):
    """Token budgeting: dense text must not slip past the limit, and code must win over bulk data."""

    def test_dense_markup_is_not_undercounted(self):
        # Inline SVG path data tokenizes at ~1.3 chars/token; a flat chars/4 estimate was 3x low.
        svg = '<path d="' + "M32,62L54,32 58,53 " * 2000 + '"/>'
        self.assertGreater(srv.estimate_tokens(svg), len(svg) / 2)
        prose = "The quick brown fox jumps over the lazy dog. " * 200
        self.assertLess(srv.estimate_tokens(prose), len(prose) / 3)
        self.assertEqual(srv.estimate_tokens(""), 0)
        self.assertGreaterEqual(srv.estimate_tokens("\u65e5\u672c\u8a9e" * 100), 300)  # ~1 token per CJK char

    def test_budget_is_enforced_in_estimated_tokens(self):
        (self.root / "src" / "art.svg").write_text("<svg>" + "1,2 3,4 " * 5000 + "</svg>")
        _, meta = srv.collect_files(["src/"], self.root, max_tokens=5_000)
        self.assertLessEqual(meta["approx_tokens"], 5_000)
        self.assertIn("src/art.svg", meta["omitted"])

    def test_code_is_read_before_translation_catalogs(self):
        (self.root / "_messages").mkdir()
        for lang in ("ar", "de", "en", "fr"):  # sorts before src/
            (self.root / "_messages" / f"{lang}.json").write_text(json.dumps({"k%d" % i: "v" * 40 for i in range(300)}))
        (self.root / "src" / "main.js").write_text("export function main() { return 1; }\n" * 50)
        _, meta = srv.collect_files(["."], self.root, max_tokens=4_000)
        self.assertIn("src/main.js", meta["files"])
        self.assertIn("src/app.py", meta["files"])
        self.assertTrue(any(f.startswith("_messages/") for f in meta["omitted"]))

    def test_explicit_files_keep_first_place(self):
        (self.root / "data.json").write_text("{}")
        _, meta = srv.collect_files(["data.json", "src/app.py"], self.root)
        self.assertEqual(meta["files"][0], "data.json")

    def test_priority_tiers(self):
        self.assertEqual(srv.file_priority("static/src/app.js"), 0)
        self.assertEqual(srv.file_priority("README.md"), 0)
        self.assertEqual(srv.file_priority("static/scenes/x/index.html"), 1)
        self.assertEqual(srv.file_priority("_messages/fr.json"), 2)
        self.assertEqual(srv.file_priority("package-lock.json"), 2)
        self.assertEqual(srv.file_priority("img/logo.svg"), 2)
        self.assertEqual(srv.file_priority("dist/app.min.js"), 2)
        self.assertEqual(srv.file_priority("CHANGELOG/CHANGELOG-1.10.md"), 2)
        self.assertEqual(srv.file_priority("CHANGELOG.md"), 2)
        self.assertEqual(srv.file_priority("LICENSE"), 2)
        self.assertEqual(srv.file_priority("pkg/apis/zz_generated.deepcopy.go"), 2)
        self.assertEqual(srv.file_priority("api/v1/types.pb.go"), 2)
        self.assertEqual(srv.file_priority("proto/user_pb2.py"), 2)
        self.assertEqual(srv.file_priority("pkg/history.go"), 0)
        self.assertEqual(srv.file_priority("src/licenseCheck.ts"), 0)


    def test_glob_semantics(self):
        rx = srv._glob_regex
        self.assertTrue(rx("*.py").fullmatch("a.py"))
        self.assertFalse(rx("*.py").fullmatch("src/a.py"))
        self.assertTrue(rx("**/*.py").fullmatch("a.py"))
        self.assertTrue(rx("**/*.py").fullmatch("src/x/a.py"))
        self.assertTrue(rx("src/**").fullmatch("src/x/a.py"))
        self.assertTrue(rx("src/[ab].py").fullmatch("src/a.py"))
        self.assertFalse(rx("src/[!ab].py").fullmatch("src/a.py"))

    def test_fair_order_lets_every_directory_take_turns(self):
        rels = [f"big/f{i}.js" for i in range(50)] + ["core/a.js", "core/b.js", "z.md"]
        head = srv.fair_order(rels)[:6]
        self.assertIn("core/a.js", head)
        self.assertIn("z.md", head)

    def test_large_directory_cannot_starve_the_rest(self):
        (self.root / "aaa_scenes").mkdir()
        for i in range(40):
            (self.root / "aaa_scenes" / f"s{i}.js").write_text("let x = %d;\n" % i * 200)
        (self.root / "zcore").mkdir()
        (self.root / "zcore" / "loader.js").write_text("export const load = () => 1;\n")
        _, meta = srv.collect_files(["."], self.root, max_tokens=6_000)
        self.assertTrue(meta["truncated"])
        self.assertIn("zcore/loader.js", meta["files"])

    def test_tracked_build_dir_is_read_but_node_modules_never(self):
        (self.root / "build").mkdir()
        (self.root / "build" / "tool.js").write_text("module.exports = 1;\n")
        (self.root / "node_modules" / "dep").mkdir(parents=True)
        (self.root / "node_modules" / "dep" / "index.js").write_text("nm-canary\n")
        subprocess.run(["git", "add", "-f", "-A"], cwd=self.root, check=True)
        corpus, meta = srv.collect_files(["."], self.root)
        self.assertIn("build/tool.js", meta["files"])
        self.assertNotIn("nm-canary", corpus)
        corpus, meta = srv.collect_files(["**/*.js"], self.root)
        self.assertIn("build/tool.js", meta["files"])
        self.assertNotIn("nm-canary", corpus)

    def test_dense_files_are_read_after_regular_code(self):
        (self.root / "a_bundle.js").write_text("var a=[" + ",".join(str(i) for i in range(20000)) + "];")
        _, meta = srv.collect_files(["."], self.root)
        self.assertEqual(meta["files"][-1], "a_bundle.js")

    def test_one_huge_file_cannot_displace_many_small_ones(self):
        (self.root / "aa_huge.py").write_text("def f():\n    return 'x'\n" * 3000)
        for i in range(20):
            (self.root / "src" / f"mod{i}.py").write_text("def g%d():\n    return %d\n" % (i, i))
        _, meta = srv.collect_files(["."], self.root, max_tokens=12_000)
        self.assertEqual(sum(f.startswith("src/mod") for f in meta["files"]), 20)
        self.assertIn("aa_huge.py", meta["omitted"])

    def test_files_past_the_budget_are_not_opened(self):
        for i in range(600):
            (self.root / "src" / f"m{i}.py").write_text("x = 1\n" * 400)
        real_read = Path.read_text
        calls = []
        def counting(self_path, *a, **k):
            calls.append(self_path)
            return real_read(self_path, *a, **k)
        with mock.patch.object(Path, "read_text", counting):
            _, meta = srv.collect_files(["src/"], self.root, max_tokens=3_000)
        self.assertTrue(meta["truncated"])
        self.assertLess(len(calls), 260)
        self.assertGreater(meta["skipped"]["over_budget"], 500)

    def test_symlink_to_gitignored_file_is_refused(self):
        (self.root / "secrets.local.json").write_text("symlinked-ignored-canary\n")
        (self.root / ".gitignore").write_text("*.log\nsecrets.local.json\n")
        os.symlink(self.root / "secrets.local.json", self.root / "src" / "settings.json")
        subprocess.run(["git", "add", "src/settings.json", ".gitignore"], cwd=self.root, check=True)
        for paths in (["."], ["src/"], ["src/*.json"], ["**/*.json"]):
            try:
                corpus, _ = srv.collect_files(paths, self.root)
            except srv.ToolError:
                continue  # the symlink was the only match and was refused
            self.assertNotIn("symlinked-ignored-canary", corpus, paths)

    def test_tracked_but_ignored_file_is_skipped(self):
        (self.root / "local.cfg").write_text("tracked-ignored-canary\n")
        subprocess.run(["git", "add", "local.cfg"], cwd=self.root, check=True)
        (self.root / ".gitignore").write_text("*.log\nlocal.cfg\n")
        corpus, meta = srv.collect_files(["."], self.root)
        self.assertNotIn("tracked-ignored-canary", corpus)
        self.assertIn("local.cfg", meta["skipped"]["ignored"])

    def test_token_limit_error_has_actionable_hint(self):
        msg = srv._http_error_message(400, json.dumps({"error": {"message":
              "The input token count (1210000) exceeds the maximum number of tokens allowed (1048576)."}}), "m")
        self.assertIn("GEMINI4_MAX_CONTEXT_TOKENS", msg)


if __name__ == "__main__":
    unittest.main()
