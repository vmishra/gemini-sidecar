"""Tests for router/gemini4_gateway.py. Standard library only; no network calls."""

import email.message
import io
import json
import os
import stat
import sys
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request
from contextlib import redirect_stdout
from unittest import mock

for _name in ("GEMINI_API_KEY", "GOOGLE_API_KEY", "ANTHROPIC_UPSTREAM_KEY", "ANTHROPIC_API_KEY",
              "GOOGLE_GENAI_USE_VERTEXAI", "GEMINI4_SESSION_BUDGET_USD", "GEMINI4_GLOBAL_BUDGET_USD",
              "GEMINI4_PRICES_JSON", "GEMINI4_SECURITY_MODEL"):
    os.environ.pop(_name, None)

_TMP_HOME = tempfile.mkdtemp(prefix="gemini4-gw-test-")
os.environ["HOME"] = _TMP_HOME
os.environ["GEMINI4_GATEWAY_TOKEN"] = "test-token-0123456789abcdef0123456789"
os.environ["GEMINI4_GATEWAY_LOG"] = "0"
TOKEN = os.environ["GEMINI4_GATEWAY_TOKEN"]

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "router"))
import gemini4_gateway as gw  # noqa: E402

import http.client  # noqa: E402


def reset_state():
    gw.SESSION_PINS.clear()
    gw.SESSION_SPEND_USD.clear()
    gw.THOUGHT_SIGNATURE_VAULT.clear()
    with gw.BUDGET_LOCK:
        gw.GLOBAL_SPEND_USD["settled"] = 0.0
        gw.GLOBAL_SPEND_USD["reserved"] = 0.0


class FakeResponse:
    """Minimal stand-in for the object returned by urllib.request.urlopen."""

    def __init__(self, body, status=200, content_type="application/json", chunks=None):
        self._buf = io.BytesIO(body)
        self._chunks = list(chunks) if chunks is not None else None
        self.status = status
        self.headers = email.message.Message()
        self.headers["Content-Type"] = content_type

    def read(self, n=-1):
        return self._buf.read(n)

    def read1(self, n=-1):
        if self._chunks is not None:
            return self._chunks.pop(0) if self._chunks else b""
        return self._buf.read(n)

    def close(self):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def gemini_ok(parts, finish="STOP", usage=None):
    return {
        "candidates": [{"content": {"role": "model", "parts": parts}, "finishReason": finish}],
        "usageMetadata": usage if usage is not None else {
            "promptTokenCount": 1200, "cachedContentTokenCount": 200,
            "candidatesTokenCount": 30, "thoughtsTokenCount": 20,
        },
    }


class Recorder:
    """Callable that replaces urlopen, records requests and returns or raises a preset result."""

    def __init__(self, result=None, error=None, delay=0.0):
        self.result = result
        self.error = error
        self.delay = delay
        self.requests = []

    def __call__(self, req, timeout=None, context=None):
        self.requests.append(req)
        if self.delay:
            time.sleep(self.delay)
        if self.error is not None:
            raise self.error
        if isinstance(self.result, FakeResponse):
            return self.result
        return FakeResponse(json.dumps(self.result).encode("utf-8"))


def http_error(code, body):
    return urllib.error.HTTPError("https://upstream.invalid", code, "error", email.message.Message(),
                                  io.BytesIO(json.dumps(body).encode("utf-8")))


def parse_sse(raw):
    events = []
    for frame in raw.decode("utf-8").split("\n\n"):
        if not frame.strip():
            continue
        name, data = None, None
        for line in frame.split("\n"):
            if line.startswith("event: "):
                name = line[len("event: "):]
            elif line.startswith("data: "):
                data = json.loads(line[len("data: "):])
        events.append((name, data))
    return events


class ServerTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = gw.ReusableGatewayHTTPServer(("127.0.0.1", 0), gw.GatewayHandler)
        cls.port = cls.server.server_address[1]
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()

    def setUp(self):
        reset_state()

    def request(self, method, path, body=None, headers=None, token=True, raw=None):
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        hdrs = {"Content-Type": "application/json"}
        if token:
            hdrs["x-api-key"] = TOKEN
        hdrs.update(headers or {})
        data = raw if raw is not None else (json.dumps(body).encode("utf-8") if body is not None else None)
        conn.request(method, path, body=data, headers=hdrs)
        resp = conn.getresponse()
        payload = resp.read()
        conn.close()
        return resp, payload

    def messages_body(self, **overrides):
        body = {
            "model": "claude-gemini-3.8-flash",
            "max_tokens": 1024,
            "messages": [{"role": "user", "content": "List the files."}],
            "metadata": {"user_id": "session-test"},
        }
        body.update(overrides)
        return body


class AuthAndHostTests(ServerTestCase):
    def test_token_required(self):
        body = {"messages": [{"role": "user", "content": "hello"}]}
        resp, payload = self.request("POST", "/v1/messages/count_tokens", body, token=False)
        self.assertEqual(resp.status, 401)
        self.assertEqual(json.loads(payload)["error"]["type"], "authentication_error")
        resp, _ = self.request("GET", "/v1/models", token=False)
        self.assertEqual(resp.status, 401)
        resp, _ = self.request("POST", "/v1/messages/count_tokens", body,
                               token=False, headers={"x-api-key": "wrong"})
        self.assertEqual(resp.status, 401)

    def test_token_accepted(self):
        body = {"messages": [{"role": "user", "content": "hello"}]}
        resp, payload = self.request("POST", "/v1/messages/count_tokens", body)
        self.assertEqual(resp.status, 200)
        self.assertGreater(json.loads(payload)["input_tokens"], 0)
        resp, _ = self.request("POST", "/anthropic/v1/messages/count_tokens", body, token=False,
                               headers={"Authorization": "Bearer " + TOKEN})
        self.assertEqual(resp.status, 200)
        resp, payload = self.request("GET", "/v1/models")
        self.assertEqual(resp.status, 200)
        ids = [m["id"] for m in json.loads(payload)["data"]]
        self.assertIn("claude-gemini-4-carbon", ids)

    def test_host_rejected(self):
        resp, _ = self.request("GET", "/health", token=False, headers={"Host": f"evil.example:{self.port}"})
        self.assertEqual(resp.status, 403)
        resp, _ = self.request("GET", "/v1/models", headers={"Host": "127.0.0.1:1"})
        self.assertEqual(resp.status, 403)
        resp, _ = self.request("GET", "/v1/models", headers={"Host": f"localhost:{self.port}"})
        self.assertEqual(resp.status, 200)

    def test_origin_rejected(self):
        resp, _ = self.request("GET", "/v1/models", headers={"Origin": "https://evil.example"})
        self.assertEqual(resp.status, 403)
        self.assertIsNone(resp.getheader("Access-Control-Allow-Origin"))

    def test_options_not_allowed(self):
        resp, _ = self.request("OPTIONS", "/v1/messages", token=False)
        self.assertEqual(resp.status, 405)
        self.assertIsNone(resp.getheader("Access-Control-Allow-Origin"))

    def test_health_minimal(self):
        resp, payload = self.request("GET", "/health", token=False)
        self.assertEqual(resp.status, 200)
        self.assertEqual(json.loads(payload), {"status": "ok", "version": gw.VERSION})

    def test_debug_endpoints_removed(self):
        resp, _ = self.request("GET", "/api/status")
        self.assertEqual(resp.status, 404)
        resp, _ = self.request("POST", "/api/simulate-route", {"prompt": "x"})
        self.assertEqual(resp.status, 404)


class BodyHandlingTests(ServerTestCase):
    def test_body_too_large(self):
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        conn.putrequest("POST", "/v1/messages")
        conn.putheader("x-api-key", TOKEN)
        conn.putheader("Content-Type", "application/json")
        conn.putheader("Content-Length", str(gw.MAX_BODY_BYTES + 1))
        conn.endheaders()
        resp = conn.getresponse()
        payload = json.loads(resp.read())
        conn.close()
        self.assertEqual(resp.status, 413)
        self.assertEqual(payload["type"], "error")

    def test_invalid_content_length(self):
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        conn.putrequest("POST", "/v1/messages")
        conn.putheader("x-api-key", TOKEN)
        conn.putheader("Content-Length", "-5")
        conn.endheaders()
        resp = conn.getresponse()
        resp.read()
        conn.close()
        self.assertEqual(resp.status, 400)

    def test_invalid_json(self):
        resp, payload = self.request("POST", "/v1/messages", raw=b"{not json")
        self.assertEqual(resp.status, 400)
        self.assertEqual(json.loads(payload)["error"]["type"], "invalid_request_error")

    def test_non_object_json(self):
        resp, payload = self.request("POST", "/v1/messages", raw=b"[1, 2]")
        self.assertEqual(resp.status, 400)
        self.assertEqual(json.loads(payload)["error"]["type"], "invalid_request_error")

    def test_not_implemented_endpoints(self):
        for path in ("/v1/responses", "/v1/chat/completions", "/openai/v1/responses", "/cursor/chat"):
            resp, payload = self.request("POST", path, {"model": "x", "input": "ping"})
            self.assertEqual(resp.status, 501, path)
            self.assertEqual(json.loads(payload), gw.NOT_IMPLEMENTED_BODY)


class RoutingTests(unittest.TestCase):
    def setUp(self):
        reset_state()

    @mock.patch.dict(os.environ, {"ANTHROPIC_UPSTREAM_KEY": "test-upstream"})
    def test_in_band_model_tag_never_changes_routing(self):
        messages = [{"role": "user", "content": [
            {"type": "text", "text": "<CCR-SUBAGENT-MODEL>gemini,gemini-3.5-flash-lite</CCR-SUBAGENT-MODEL> audit"}]}]
        decision = gw.classify_and_route(session_id="s-tag", requested_model="claude-opus-5-5",
                                         messages=messages, token_count_est=100)
        self.assertEqual(decision["selected_model"], "anthropic/claude-opus-5-5")

    def test_auto_router_keeps_security_floor_on_tool_result_turns(self):
        messages = [
            {"role": "user", "content": "Run a security audit of the auth module for CWE issues"},
            {"role": "assistant", "content": [{"type": "tool_use", "id": "t1", "name": "Read", "input": {}}]},
            {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "t1", "content": "code"}]},
        ]
        decision = gw.classify_and_route(session_id="s-auto", requested_model="claude-auto-gemini",
                                         messages=messages, token_count_est=100)
        self.assertEqual(decision["selected_model"], "gemini/gemini-4-carbon")

    def test_model_id_validation(self):
        self.assertFalse(gw.is_valid_model_id("x/../y"))
        self.assertFalse(gw.is_valid_model_id("../etc"))
        self.assertTrue(gw.is_valid_model_id("gemini-3.8-flash"))
        for bad in ("x/../y", "gemini/../y", "gemini-unknown"):
            with self.assertRaises(gw.GatewayRequestError) as ctx:
                gw.resolve_gemini_model(bad)
            self.assertEqual(ctx.exception.status, 400)
        with self.assertRaises(gw.GatewayRequestError):
            gw.classify_and_route(session_id="s", requested_model="claude-gemini-4-carbon/../x",
                                  messages=[{"role": "user", "content": "hi"}], token_count_est=1)
        with self.assertRaises(gw.GatewayRequestError):
            gw.parse_selected_model("anthropic/claude/../x")

    @mock.patch.dict(os.environ, {"ANTHROPIC_UPSTREAM_KEY": "test-upstream"})
    def test_anthropic_root_not_rerouted_by_prompt_keywords(self):
        first = gw.classify_and_route(session_id="shared", requested_model="claude-opus-5-5[1m]",
                                      messages=[{"role": "user", "content": "Plan the refactor"}],
                                      token_count_est=100)
        self.assertEqual(first["selected_model"], "anthropic/claude-opus-5-5")
        second = gw.classify_and_route(session_id="shared", requested_model="claude-opus-5-5",
                                       messages=[{"role": "user", "content": "Run a CWE-89 security audit"}],
                                       token_count_est=200_000)
        self.assertEqual(second["selected_model"], "anthropic/claude-opus-5-5")
        self.assertEqual(gw.SESSION_PINS.get("shared")["model"], "anthropic/claude-opus-5-5")

    def test_unmapped_model_without_upstream_key_uses_flash(self):
        os.environ.pop("ANTHROPIC_UPSTREAM_KEY", None)
        decision = gw.classify_and_route(session_id="bg", requested_model="claude-sonnet-4-6",
                                         messages=[{"role": "user", "content": "security check of this command"}],
                                         token_count_est=100)
        self.assertEqual(decision["selected_model"], "gemini/gemini-3.8-flash")
        self.assertEqual(decision["rule_matched"], "unmapped_model_default")

    def test_failover_pin_not_overwritten(self):
        gw.pin_failover("fo", "gemini/gemini-4-carbon", 1)
        decision = gw.classify_and_route(session_id="fo", requested_model="claude-opus-5-5",
                                         messages=[{"role": "user", "content": "Continue"}],
                                         token_count_est=100)
        self.assertEqual(decision["selected_model"], "gemini/gemini-4-carbon")
        gw.classify_and_route(session_id="fo", requested_model="claude-gemini-3.8-flash",
                              messages=[{"role": "user", "content": "x"}], token_count_est=100)
        pin = gw.SESSION_PINS.get("fo")
        self.assertTrue(pin["failover"])
        self.assertEqual(pin["model"], "gemini/gemini-4-carbon")

    def test_non_string_session_id(self):
        gw.classify_and_route(session_id=12345, requested_model="claude-opus-5-5",
                              messages=[{"role": "user", "content": "hi"}], token_count_est=1)
        self.assertIn("12345", gw.SESSION_PINS)

    def test_session_map_bounded(self):
        lru = gw.BoundedLRU(3)
        for i in range(5):
            lru.set(str(i), i)
        self.assertEqual(len(lru), 3)
        self.assertNotIn("0", lru)

    def test_fallback_session_id_uses_system_prompt(self):
        a = gw.derive_session_id({"system": "A", "messages": [{"role": "user", "content": "hi"}]})
        b = gw.derive_session_id({"system": "B", "messages": [{"role": "user", "content": "hi"}]})
        self.assertNotEqual(a, b)
        self.assertEqual(gw.derive_session_id({"metadata": {"user_id": 42}}), "42")


class TranslationTests(unittest.TestCase):
    def test_tool_result_and_text_split_into_separate_turns(self):
        body = {"max_tokens": 100, "messages": [
            {"role": "user", "content": "read a.txt"},
            {"role": "assistant", "content": [{"type": "tool_use", "id": "toolu_1", "name": "Read", "input": {"p": "a"}}]},
            {"role": "user", "content": [
                {"type": "tool_result", "tool_use_id": "toolu_1", "content": "hello"},
                {"type": "text", "text": "<system-reminder>note</system-reminder>"},
            ]},
        ]}
        contents = gw.translate_anthropic_to_gemini_payload(body, "gemini-3.8-flash")["contents"]
        self.assertEqual([c["role"] for c in contents], ["user", "model", "user", "user"])
        self.assertIn("functionResponse", contents[2]["parts"][0])
        self.assertEqual(len(contents[2]["parts"]), 1)
        self.assertIn("text", contents[3]["parts"][0])

    def test_tool_schema_passed_through_as_json_schema(self):
        schema = {
            "$schema": "http://json-schema.org/draft-07/schema#",
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "title": {"type": "string", "title": "Title"},
                "count": {"type": "integer", "exclusiveMinimum": 0},
            },
            "required": ["title"],
        }
        body = {"messages": [{"role": "user", "content": "x"}], "max_tokens": 100,
                "tools": [{"name": "create_issue", "description": "d", "input_schema": schema}]}
        payload = gw.translate_anthropic_to_gemini_payload(body, "gemini-3.8-flash")
        decl = payload["tools"][0]["functionDeclarations"][0]
        self.assertEqual(decl["parametersJsonSchema"], schema)
        self.assertNotIn("parameters", decl)

    def test_max_tokens_not_raised(self):
        body = {"messages": [{"role": "user", "content": "x"}], "max_tokens": 8192, "temperature": 0.2}
        payload = gw.translate_anthropic_to_gemini_payload(body, "gemini-4-carbon")
        self.assertEqual(payload["generationConfig"]["maxOutputTokens"], 8192)
        self.assertNotIn("temperature", payload["generationConfig"])
        body["max_tokens"] = 200000
        payload = gw.translate_anthropic_to_gemini_payload(body, "gemini-3.8-flash")
        self.assertEqual(payload["generationConfig"]["maxOutputTokens"], 65536)
        payload = gw.translate_anthropic_to_gemini_payload(body, "gemini-4-carbon")
        self.assertEqual(payload["generationConfig"]["maxOutputTokens"], 32768)  # one long-decode segment

    def test_pro_class_models_get_high_thinking(self):
        body = {"messages": [{"role": "user", "content": "x"}], "max_tokens": 100}
        for model in ("gemini-4-carbon", "gemini/gemini-4-carbon", "gemini-4-argon"):
            payload = gw.translate_anthropic_to_gemini_payload(body, model)
            self.assertEqual(payload["generationConfig"]["thinkingConfig"]["thinkingLevel"], "HIGH", model)
        payload = gw.translate_anthropic_to_gemini_payload(body, "gemini-3.8-flash")
        self.assertEqual(payload["generationConfig"]["thinkingConfig"]["thinkingLevel"], "LOW")

    def test_continuation_finish_maps_to_max_tokens(self):
        resp = {"candidates": [{"content": {"parts": [{"text": "partial"}]}, "finishReason": "CONTINUATION",
                                "continuationToken": "t"}], "usageMetadata": {"promptTokenCount": 5, "candidatesTokenCount": 2}}
        out = gw.gemini_response_to_anthropic(resp, "claude-gemini-4-carbon")
        self.assertEqual(out["stop_reason"], "max_tokens")

    def test_system_merge_and_thinking_dropped(self):
        body = {
            "system": "Top.",
            "messages": [
                {"role": "system", "content": "Embedded."},
                {"role": "user", "content": "Go."},
                {"role": "assistant", "content": [
                    {"type": "thinking", "thinking": "...", "signature": "sig"},
                    {"type": "tool_use", "id": "a", "name": "Read", "input": {}},
                    {"type": "tool_use", "id": "b", "name": "Read", "input": {}},
                ]},
            ],
        }
        payload = gw.translate_anthropic_to_gemini_payload(body, "gemini-3.8-flash")
        self.assertIn("Embedded.", payload["systemInstruction"]["parts"][0]["text"])
        self.assertEqual(len(payload["contents"]), 2)
        parts = payload["contents"][1]["parts"]
        self.assertEqual(len(parts), 2)
        self.assertEqual(parts[0]["thoughtSignature"], "skip_thought_signature_validator")
        self.assertNotIn("thoughtSignature", parts[1])

    def test_finish_reasons(self):
        msg = gw.gemini_response_to_anthropic(gemini_ok([{"text": "partial"}], finish="MAX_TOKENS"), "m")
        self.assertEqual(msg["stop_reason"], "max_tokens")
        with self.assertRaises(gw.GatewayRequestError) as ctx:
            gw.gemini_response_to_anthropic(gemini_ok([], finish="SAFETY"), "m")
        self.assertEqual(ctx.exception.status, 400)
        with self.assertRaises(gw.GatewayRequestError):
            gw.gemini_response_to_anthropic({"candidates": [], "promptFeedback": {"blockReason": "SAFETY"}}, "m")

    def test_usage_from_metadata(self):
        usage = gw.gemini_usage_to_anthropic({"promptTokenCount": 1000, "cachedContentTokenCount": 400,
                                              "candidatesTokenCount": 10, "thoughtsTokenCount": 5})
        self.assertEqual(usage["input_tokens"], 600)
        self.assertEqual(usage["cache_read_input_tokens"], 400)
        self.assertEqual(usage["output_tokens"], 15)
        self.assertEqual(gw.gemini_usage_to_anthropic(None)["output_tokens"], 0)


class GeminiHttpTests(ServerTestCase):
    def setUp(self):
        super().setUp()
        self.env = mock.patch.dict(os.environ, {"GEMINI_API_KEY": "fake-gemini-key"})
        self.env.start()

    def tearDown(self):
        self.env.stop()

    def test_sse_event_order_with_tool_call(self):
        rec = Recorder(gemini_ok([
            {"text": "Reading it now."},
            {"functionCall": {"name": "Read", "args": {"path": "a.py"}}, "thoughtSignature": "sig-1"},
        ]))
        with mock.patch.object(urllib.request, "urlopen", rec):
            resp, payload = self.request("POST", "/v1/messages", self.messages_body(stream=True))
        self.assertEqual(resp.status, 200)
        self.assertTrue(resp.getheader("Content-Type").startswith("text/event-stream"))
        events = parse_sse(payload)
        names = [e[0] for e in events]
        self.assertEqual(names, [
            "message_start",
            "content_block_start", "content_block_delta", "content_block_stop",
            "content_block_start", "content_block_delta", "content_block_stop",
            "message_delta", "message_stop",
        ])
        start_usage = events[0][1]["message"]["usage"]
        self.assertEqual(start_usage["input_tokens"], 1000)
        self.assertEqual(start_usage["cache_read_input_tokens"], 200)
        tool_start = events[4][1]["content_block"]
        self.assertEqual(tool_start["type"], "tool_use")
        self.assertRegex(tool_start["id"], r"^[a-zA-Z0-9_-]+$")
        self.assertEqual(json.loads(events[5][1]["delta"]["partial_json"]), {"path": "a.py"})
        self.assertEqual(events[7][1]["delta"]["stop_reason"], "tool_use")
        self.assertEqual(events[7][1]["usage"]["output_tokens"], 50)
        self.assertEqual(gw.THOUGHT_SIGNATURE_VAULT.get(tool_start["id"]), "sig-1")

    def test_ping_sent_while_waiting(self):
        rec = Recorder(gemini_ok([{"text": "done"}]), delay=0.3)
        with mock.patch.object(urllib.request, "urlopen", rec), mock.patch.object(gw, "PING_INTERVAL_S", 0.05):
            resp, payload = self.request("POST", "/v1/messages", self.messages_body(stream=True))
        names = [e[0] for e in parse_sse(payload)]
        self.assertEqual(names[0], "ping")
        first_real = names.index("message_start")
        self.assertTrue(all(n == "ping" for n in names[:first_real]))
        self.assertEqual(names[-2:], ["message_delta", "message_stop"])

    def test_api_key_in_header_not_url(self):
        rec = Recorder(gemini_ok([{"text": "ok"}]))
        with mock.patch.object(urllib.request, "urlopen", rec):
            resp, payload = self.request("POST", "/v1/messages", self.messages_body())
        self.assertEqual(resp.status, 200)
        req = rec.requests[0]
        self.assertNotIn("key=", req.full_url)
        self.assertNotIn("fake-gemini-key", req.full_url)
        self.assertTrue(req.full_url.endswith("/models/gemini-3.8-flash:generateContent"))
        self.assertEqual(req.get_header("X-goog-api-key"), "fake-gemini-key")
        msg = json.loads(payload)
        self.assertEqual(msg["content"], [{"type": "text", "text": "ok"}])
        self.assertEqual(msg["stop_reason"], "end_turn")

    def test_upstream_401_maps_to_anthropic_error(self):
        rec = Recorder(error=http_error(401, {"error": {"message": "API key not valid"}}))
        with mock.patch.object(urllib.request, "urlopen", rec):
            resp, payload = self.request("POST", "/v1/messages", self.messages_body())
            self.assertEqual(resp.status, 401)
            data = json.loads(payload)
            self.assertEqual(data["type"], "error")
            self.assertEqual(data["error"]["type"], "authentication_error")
            rec.error = http_error(401, {"error": {"message": "API key not valid"}})
            resp, payload = self.request("POST", "/v1/messages", self.messages_body(stream=True))
            self.assertEqual(resp.status, 401)
            self.assertEqual(json.loads(payload)["error"]["type"], "authentication_error")

    def test_upstream_429_maps_to_rate_limit(self):
        rec = Recorder(error=http_error(429, {"error": {"message": "quota"}}))
        with mock.patch.object(urllib.request, "urlopen", rec):
            resp, payload = self.request("POST", "/v1/messages", self.messages_body())
        self.assertEqual(resp.status, 429)
        self.assertEqual(json.loads(payload)["error"]["type"], "rate_limit_error")

    def test_missing_credentials(self):
        os.environ.pop("GEMINI_API_KEY", None)
        resp, payload = self.request("POST", "/v1/messages", self.messages_body())
        self.assertEqual(resp.status, 401)
        self.assertEqual(json.loads(payload)["error"]["type"], "authentication_error")

    def test_safety_block_is_error(self):
        rec = Recorder({"candidates": [], "promptFeedback": {"blockReason": "SAFETY"}})
        with mock.patch.object(urllib.request, "urlopen", rec):
            resp, payload = self.request("POST", "/v1/messages", self.messages_body())
        self.assertEqual(resp.status, 400)
        self.assertEqual(json.loads(payload)["type"], "error")

    def test_invalid_model_rejected_over_http(self):
        rec = Recorder(gemini_ok([{"text": "ok"}]))
        with mock.patch.object(urllib.request, "urlopen", rec):
            resp, _ = self.request("POST", "/v1/messages", self.messages_body(model="claude-gemini-4-carbon/../x"))
        self.assertEqual(resp.status, 400)
        self.assertEqual(rec.requests, [])

    def test_session_budget_cap_blocks_before_call(self):
        rec = Recorder(gemini_ok([{"text": "ok"}]))
        with mock.patch.object(urllib.request, "urlopen", rec), \
                mock.patch.dict(os.environ, {"GEMINI4_SESSION_BUDGET_USD": "0.001"}):
            resp, payload = self.request("POST", "/v1/messages", self.messages_body(max_tokens=60000))
        self.assertEqual(resp.status, 403)
        self.assertEqual(json.loads(payload)["error"]["type"], "permission_error")
        self.assertEqual(rec.requests, [])

    def test_budget_settles_against_actual_usage(self):
        usage = {"promptTokenCount": 1000, "cachedContentTokenCount": 0, "candidatesTokenCount": 100}
        rec = Recorder(gemini_ok([{"text": "ok"}], usage=usage))
        with mock.patch.object(urllib.request, "urlopen", rec):
            resp, _ = self.request("POST", "/v1/messages", self.messages_body(max_tokens=60000))
        self.assertEqual(resp.status, 200)
        entry = gw.SESSION_SPEND_USD.get("session-test")
        expected = (1000 * 1.50 + 100 * 7.50) / 1_000_000.0  # Vertex list price for gemini-3.8-flash
        self.assertAlmostEqual(entry["settled"], expected, places=9)
        self.assertAlmostEqual(entry["reserved"], 0.0, places=9)
        self.assertAlmostEqual(gw.GLOBAL_SPEND_USD["settled"], expected, places=9)

    def test_failed_call_not_charged(self):
        rec = Recorder(error=http_error(500, {"error": {"message": "boom"}}))
        with mock.patch.object(urllib.request, "urlopen", rec):
            resp, _ = self.request("POST", "/v1/messages", self.messages_body())
        self.assertEqual(resp.status, 500)
        entry = gw.SESSION_SPEND_USD.get("session-test")
        self.assertEqual(entry["settled"], 0.0)
        self.assertAlmostEqual(entry["reserved"], 0.0, places=9)

    def test_global_budget_cap(self):
        with mock.patch.dict(os.environ, {"GEMINI4_GLOBAL_BUDGET_USD": "0.01"}):
            with gw.BUDGET_LOCK:
                gw.GLOBAL_SPEND_USD["settled"] = 0.0099
            ok, _, message = gw.reserve_budget("other-session", "gemini-3.8-flash", 1000, 1000)
        self.assertFalse(ok)
        self.assertIn("GEMINI4_GLOBAL_BUDGET_USD", message)


class AnthropicPassthroughTests(ServerTestCase):
    def test_original_bytes_and_headers_forwarded_and_stream_relayed(self):
        body = {
            "model": "claude-opus-5-5",
            "max_tokens": 1024,
            "stream": True,
            "metadata": {"user_id": "anth-session"},
            "messages": [
                {"role": "user", "content": "hi"},
                {"role": "assistant", "content": [{"type": "thinking", "thinking": "t", "signature": "s"},
                                                  {"type": "text", "text": "hello"}]},
                {"role": "user", "content": "plan it"},
            ],
        }
        raw = json.dumps(body, indent=1).encode("utf-8")
        chunks = [
            b'event: message_start\ndata: {"type":"message_start","message":{"usage":{"input_tokens":10,"output_tokens":1}}}\n\n',
            b'event: message_delta\ndata: {"type":"message_delta","usage":{"output_tokens":7}}\n\n',
            b'event: message_stop\ndata: {"type":"message_stop"}\n\n',
        ]
        rec = Recorder(FakeResponse(b"", content_type="text/event-stream", chunks=chunks))
        with mock.patch.object(urllib.request, "urlopen", rec), \
                mock.patch.dict(os.environ, {"ANTHROPIC_UPSTREAM_KEY": "upstream-key"}):
            resp, payload = self.request("POST", "/v1/messages", raw=raw,
                                         headers={"anthropic-version": "2023-06-01",
                                                  "anthropic-beta": "context-1m-2025-08-07"})
        self.assertEqual(resp.status, 200)
        self.assertEqual(payload, b"".join(chunks))
        req = rec.requests[0]
        self.assertEqual(req.full_url, "https://api.anthropic.com/v1/messages")
        self.assertEqual(req.data, raw)
        self.assertEqual(req.get_header("X-api-key"), "upstream-key")
        self.assertEqual(req.get_header("Anthropic-beta"), "context-1m-2025-08-07")
        self.assertEqual(req.get_header("Anthropic-version"), "2023-06-01")
        expected = (10 * 4.00 + 7 * 20.00) / 1_000_000.0
        self.assertAlmostEqual(gw.SESSION_SPEND_USD.get("anth-session")["settled"], expected, places=9)

    def test_upstream_error_status_passed_through(self):
        err = http_error(400, {"type": "error", "error": {"type": "invalid_request_error", "message": "bad"}})
        err.headers["Content-Type"] = "application/json"
        rec = Recorder(error=err)
        with mock.patch.object(urllib.request, "urlopen", rec), \
                mock.patch.dict(os.environ, {"ANTHROPIC_UPSTREAM_KEY": "upstream-key"}):
            resp, payload = self.request("POST", "/v1/messages", {
                "model": "claude-opus-5-5", "max_tokens": 10, "messages": [{"role": "user", "content": "hi"}]})
        self.assertEqual(resp.status, 400)
        self.assertEqual(json.loads(payload)["error"]["message"], "bad")

    def test_429_fails_over_to_gemini_and_pins(self):
        calls = []

        def fake(req, timeout=None, context=None):
            calls.append(req)
            if "anthropic.com" in req.full_url:
                raise http_error(429, {"type": "error", "error": {"type": "rate_limit_error", "message": "x"}})
            return FakeResponse(json.dumps(gemini_ok([{"text": "from gemini"}])).encode("utf-8"))

        env = {"ANTHROPIC_UPSTREAM_KEY": "upstream-key", "GEMINI_API_KEY": "fake-gemini-key",
               "GEMINI4_FAILOVER_TO_GEMINI": "1"}
        with mock.patch.object(urllib.request, "urlopen", fake), mock.patch.dict(os.environ, env):
            resp, payload = self.request("POST", "/v1/messages", {
                "model": "claude-opus-5-5", "max_tokens": 10, "metadata": {"user_id": "fo-http"},
                "messages": [{"role": "user", "content": "hi"}]})
        self.assertEqual(resp.status, 200)
        self.assertEqual(json.loads(payload)["content"][0]["text"], "from gemini")
        self.assertIn("gemini-4-carbon:generateContent", calls[1].full_url)
        pin = gw.SESSION_PINS.get("fo-http")
        self.assertTrue(pin["failover"])
        self.assertEqual(pin["model"], "gemini/gemini-4-carbon")

    def test_429_is_returned_not_resent_to_google_by_default(self):
        calls = []

        def fake(req, timeout=None, context=None):
            calls.append(req)
            raise http_error(429, {"type": "error", "error": {"type": "rate_limit_error", "message": "x"}})

        env = {"ANTHROPIC_UPSTREAM_KEY": "upstream-key", "GEMINI_API_KEY": "fake-gemini-key"}
        with mock.patch.object(urllib.request, "urlopen", fake), mock.patch.dict(os.environ, env):
            os.environ.pop("GEMINI4_FAILOVER_TO_GEMINI", None)
            resp, _ = self.request("POST", "/v1/messages", {
                "model": "claude-opus-5-5", "max_tokens": 10, "metadata": {"user_id": "no-fo"},
                "messages": [{"role": "user", "content": "hi"}]})
        self.assertEqual(resp.status, 429)
        self.assertEqual(len(calls), 1)
        self.assertNotIn("googleapis", calls[0].full_url)

    def test_missing_upstream_key(self):
        resp, payload = self.request("POST", "/v1/messages", {
            "model": "claude-opus-5-5", "max_tokens": 10, "messages": [{"role": "user", "content": "hi"}]})
        self.assertEqual(resp.status, 401)
        self.assertEqual(json.loads(payload)["error"]["type"], "authentication_error")


class TokenAndCliTests(unittest.TestCase):
    def test_token_file_created_with_restricted_mode(self):
        home = tempfile.mkdtemp(prefix="gemini4-gw-home-")
        with mock.patch.dict(os.environ, {"HOME": home}):
            os.environ.pop("GEMINI4_GATEWAY_TOKEN", None)
            try:
                token, path, created = gw.load_or_create_token()
                self.assertTrue(created)
                self.assertEqual(path, os.path.join(home, ".config", "gemini4", "gateway-token"))
                self.assertEqual(stat.S_IMODE(os.stat(path).st_mode), 0o600)
                self.assertEqual(stat.S_IMODE(os.stat(os.path.dirname(path)).st_mode) & 0o077, 0)
                again, _, created_again = gw.load_or_create_token()
                self.assertEqual(again, token)
                self.assertFalse(created_again)
            finally:
                os.environ["GEMINI4_GATEWAY_TOKEN"] = TOKEN

    def test_print_token_path(self):
        out = io.StringIO()
        with redirect_stdout(out):
            code = gw.main(["--print-token-path"])
        self.assertEqual(code, 0)
        self.assertEqual(out.getvalue().strip(), gw.token_file_path())
        self.assertNotIn(TOKEN, out.getvalue())

    def test_vertex_token_cached(self):
        gw._VERTEX_TOKEN_CACHE.update({"token": None, "expires": 0.0})
        proc = mock.Mock(returncode=0, stdout="vertex-token\n")
        with mock.patch.object(gw.subprocess, "run", return_value=proc) as run:
            self.assertEqual(gw._vertex_access_token(), "vertex-token")
            self.assertEqual(gw._vertex_access_token(), "vertex-token")
        self.assertEqual(run.call_count, 1)
        gw._VERTEX_TOKEN_CACHE.update({"token": None, "expires": 0.0})
        with mock.patch.object(gw.subprocess, "run", side_effect=OSError("missing")):
            with self.assertRaises(gw.GatewayRequestError):
                gw._vertex_access_token()

    def test_prices_override(self):
        with mock.patch.dict(os.environ, {"GEMINI4_PRICES_JSON": '{"gemini-4-carbon": [4.0, 0.2, 20.0]}'}):
            self.assertEqual(gw._price_for("gemini-4-carbon"), (4.0, 0.2, 20.0))
        self.assertEqual(gw._price_for("claude-sonnet-5-5"), (2.00, 0.20, 10.00))


if __name__ == "__main__":
    unittest.main()


class HardeningTests(unittest.TestCase):
    """Findings from the pre-release security review."""

    def setUp(self):
        self.home = tempfile.mkdtemp()
        self.env = mock.patch.dict(os.environ, {"HOME": self.home})
        self.env.start()
        os.environ.pop("GEMINI4_GATEWAY_TOKEN", None)

    def tearDown(self):
        self.env.stop()

    def test_short_env_token_is_refused(self):
        with mock.patch.dict(os.environ, {"GEMINI4_GATEWAY_TOKEN": "short"}):
            with self.assertRaises(RuntimeError):
                gw.load_or_create_token()

    def test_token_file_created_private_and_reused(self):
        token, path, created = gw.load_or_create_token()
        self.assertTrue(created)
        self.assertGreaterEqual(len(token), 32)
        self.assertEqual(stat.S_IMODE(os.stat(path).st_mode), 0o600)
        self.assertEqual(gw.load_or_create_token()[0], token)

    def test_loose_permissions_and_symlinks_are_refused(self):
        token, path, _ = gw.load_or_create_token()
        os.chmod(path, 0o644)
        with self.assertRaises(RuntimeError):
            gw.load_or_create_token()
        os.remove(path)
        target = os.path.join(self.home, "attacker-token")
        with open(target, "w") as fh:
            fh.write("x" * 40)
        os.symlink(target, path)
        with self.assertRaises(RuntimeError):
            gw.load_or_create_token()

    def test_non_finite_budget_is_refused(self):
        for bad in ("nan", "inf", "-1"):
            with mock.patch.dict(os.environ, {"GEMINI4_GLOBAL_BUDGET_USD": bad}):
                with self.assertRaises(RuntimeError):
                    gw._env_float("GEMINI4_GLOBAL_BUDGET_USD")

    def test_connection_cap_exists(self):
        self.assertLessEqual(gw.MAX_CONNECTIONS, 256)
        self.assertLessEqual(gw.GatewayHandler.timeout, 10)

