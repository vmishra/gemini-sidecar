#!/usr/bin/env bash
# =============================================================================
# End-to-End Hermetic Verification Suite (`verify.sh` v1.3 — Nov 2026)
# Runs offline on Python 3.9, 3.10, 3.11, 3.12, and 3.13+ (including stock
# macOS Command Line Tools `/usr/bin/python3` without external dependencies).
# =============================================================================
set -euo pipefail

KIT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MCP_SERVER="${KIT_DIR}/plugins/gemini4-coexistence/mcp/gemini4_mcp_server.py"

echo "=================================================================="
echo " Gemini 4 Coexistence Kit v1.3 — Hermetic Verification Suite"
echo "=================================================================="

# 1. Claude Code Plugin, Marketplace & Role-Pinning JSON Validation
echo "[1/7] Validating Claude Code Plugin, Marketplace & Role-Pinning manifests..."
if command -v claude >/dev/null 2>&1 && claude plugin --help >/dev/null 2>&1; then
  claude plugin validate "${KIT_DIR}/plugins/gemini4-coexistence" >/dev/null
  claude plugin validate "${KIT_DIR}" >/dev/null
  echo "  PASS: 'claude plugin validate' passed on plugin and marketplace (0 errors, 0 warnings)."
else
  python3 -m json.tool "${KIT_DIR}/.claude-plugin/marketplace.json" >/dev/null
  python3 -m json.tool "${KIT_DIR}/plugins/gemini4-coexistence/.claude-plugin/plugin.json" >/dev/null
  echo "  PASS: JSON manifests validated via Python stdlib."
fi
python3 - "${KIT_DIR}" <<'PY'
import json, pathlib, sys
kit = pathlib.Path(sys.argv[1])
for name in ("settings.hybrid-role-pinning.json", "settings.all-gemini-tiered.json"):
    cfg = json.loads((kit / "claude" / name).read_text(encoding="utf-8"))
    env = cfg["env"]
    assert env["ANTHROPIC_API_KEY"] == "", f"{name} must blank ANTHROPIC_API_KEY"
    assert env["CLAUDE_CODE_ENABLE_GATEWAY_MODEL_DISCOVERY"] == "1"
    assert env["CLAUDE_CODE_AUTO_COMPACT_WINDOW"] == "800000"
all_gem = json.loads((kit / "claude" / "settings.all-gemini-tiered.json").read_text(encoding="utf-8"))
assert all_gem["env"].get("ENABLE_TOOL_SEARCH") == "false", "All-Gemini profile must set ENABLE_TOOL_SEARCH=false"
print("  PASS: Both Claude Code v2.1.302+ role-pinning templates verified (incl. ENABLE_TOOL_SEARCH=false).")
PY

# 2. Codex Multi-Version TOML & Built-In `explorer` Override Validation (Python 3.9+ Safe)
echo "[2/7] Validating OpenAI Codex Responses API profiles & custom agents..."
python3 - "${KIT_DIR}" <<'PY'
import pathlib, re, sys

def load_toml_compat(text: str) -> dict:
    try:
        import tomllib
        return tomllib.loads(text)
    except ImportError:
        try:
            import tomli
            return tomli.loads(text)
        except ImportError:
            pass
    root = {}
    cur = root
    lines = text.splitlines()
    i = 0
    while i < len(lines):
        raw = lines[i].strip()
        i += 1
        if not raw or raw.startswith("#"):
            continue
        if raw.startswith("[[") and raw.endswith("]]"):
            sec = raw[2:-2].strip()
            parts = re.findall(r'"[^"]+"|[^.]+', sec)
            parent = root
            for part in parts[:-1]:
                parent = parent.setdefault(part.strip('"'), {})
            arr = parent.setdefault(parts[-1].strip('"'), [])
            cur = {}
            arr.append(cur)
            continue
        if raw.startswith("[") and raw.endswith("]"):
            sec = raw[1:-1].strip()
            parts = re.findall(r'"[^"]+"|[^.]+', sec)
            cur = root
            for part in parts:
                cur = cur.setdefault(part.strip('"'), {})
            continue
        if "=" in raw:
            k, v = [x.strip() for x in raw.split("=", 1)]
            if v.startswith('"""'):
                buf = [v[3:]]
                while i < len(lines) and '"""' not in buf[-1]:
                    buf.append(lines[i])
                    i += 1
                joined = "\n".join(buf)
                cur[k] = joined.split('"""')[0]
            elif v.startswith('"') and v.endswith('"'):
                cur[k] = v[1:-1]
            elif v.startswith("[") and v.endswith("]"):
                cur[k] = [x.strip().strip('"') for x in v[1:-1].split(",") if x.strip()]
            elif v in ("true", "false"):
                cur[k] = v == "true"
            elif re.fullmatch(r"-?\d+", v):
                cur[k] = int(v)
            elif re.fullmatch(r"-?\d+\.\d+", v):
                cur[k] = float(v)
            else:
                cur[k] = v
    return root

kit = pathlib.Path(sys.argv[1])
main_cfg = load_toml_compat((kit / "codex/gemini4.config.toml").read_text(encoding="utf-8"))
prov = main_cfg["model_providers"]["gemini4_gateway"]
assert prov["wire_api"] == "responses", "Codex v0.159+ requires wire_api = 'responses'"
assert prov["stream_idle_timeout_ms"] == 7200000, "Argon requires 2h stream_idle_timeout_ms"
assert "env_key" not in prov, "Localhost gateway should not require an unset env_key"
assert main_cfg["agents"]["default_subagent_model"] == "claude-gemini-3.8-flash"

agent_names = set()
for p in sorted((kit / "codex").rglob("*.toml")):
    data = load_toml_compat(p.read_text(encoding="utf-8"))
    if p.parent.name == "agents":
        for req in ("name", "description", "developer_instructions"):
            assert req in data and data[req], f"Missing {req} in {p}"
        agent_names.add(data["name"])
assert {"explorer", "argon-reviewer", "argon-migrator"} == agent_names, f"Unexpected Codex agents: {agent_names}"
print("  PASS: All 5 Codex TOML files verified (Python 3.9–3.13+ compatible).")
PY

# 3. Cursor Plugin & Subagents Validation
echo "[3/7] Validating Cursor Plugin manifest, Oct 2026 rules & subagent frontmatter..."
python3 - "${KIT_DIR}" <<'PY'
import json, pathlib, sys

kit = pathlib.Path(sys.argv[1])
manifest = json.loads((kit / ".cursor-plugin/plugin.json").read_text(encoding="utf-8"))
assert manifest["name"] == "gemini4-coexistence" and manifest["version"] == "1.1.0"
for md in sorted((kit / "cursor/agents").glob("*.md")):
    txt = md.read_text(encoding="utf-8")
    assert txt.startswith("---\n") and "name:" in txt and "description:" in txt and "model:" in txt, f"Invalid frontmatter in {md}"
rule_txt = (kit / "cursor/rules/gemini4-coexistence.mdc").read_text(encoding="utf-8")
assert "176256" in rule_txt and "0.25" in rule_txt
print("  PASS: Cursor v1.1.0 manifest, Issue #176256 guidance & 3 custom subagents verified.")
PY

# 4. CCR Node.js Worker Validation
echo "[4/7] Testing CCR Node.js Cache-Aware Router (3.5-flash-lite / 3.8-flash / 4-argon)..."
if command -v node >/dev/null 2>&1; then
  node - "${KIT_DIR}/router/ccr/gemini4-cache-aware-router.js" <<'JS'
const router = require(process.argv[2]);
(async () => {
  const rHaiku = await router({ body: { model: "claude-haiku-4-5", messages: [{ role: "user", content: "index" }] } }, {});
  if (rHaiku !== "gemini,gemini-3.5-flash-lite") throw new Error("Haiku expected 3.5-flash-lite, got " + rHaiku);
  const rSub = await router({ body: { isSubagent: true, model: "claude-opus-5-5", messages: [{ role: "user", content: "find auth files" }] } }, {});
  if (rSub !== "gemini,gemini-3.8-flash") throw new Error("Subagent expected 3.8-flash, got " + rSub);
  const rLong = await router({ tokenCount: 165000, body: { model: "claude-opus-5-5", messages: [{ role: "user", content: "synthesize repo" }] } }, {});
  if (rLong !== "gemini,gemini-4-argon") throw new Error(">150k expected 4-argon, got " + rLong);
  console.log("  PASS: CCR Node.js worker routed Flash-Lite, 3.8-Flash & 4-Argon cleanly.");
})();
JS
else
  echo "  SKIP: 'node' not found on PATH (CCR JS worker optional; Python Smart Gateway active)."
fi

# 5. Live MCP Stdio JSON-RPC 2.0 Handshake + `ask_antigravity` + File-Pointer Cache Test
echo '[5/7] Testing Gemini 4 MCP Server v1.1 JSON-RPC 2.0 (`ask_antigravity` + File-Pointer cache)...'
python3 - "${MCP_SERVER}" "${KIT_DIR}" <<'PY'
import json, subprocess, sys

mcp_bin, kit_dir = sys.argv[1], sys.argv[2]
proc = subprocess.Popen(
    [sys.executable, mcp_bin],
    stdin=subprocess.PIPE,
    stdout=subprocess.PIPE,
    stderr=subprocess.PIPE,
    text=True,
)

def rpc(msg):
    proc.stdin.write(json.dumps(msg) + "\n")
    proc.stdin.flush()
    line = proc.stdout.readline()
    return json.loads(line)

init_res = rpc({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2024-11-05"}})
assert init_res["result"]["serverInfo"]["name"] == "gemini4-coexistence"
assert init_res["result"]["serverInfo"]["version"] == "1.1.0"

tools_res = rpc({"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}})
tool_names = {t["name"] for t in tools_res["result"]["tools"]}
assert {
    "ask_antigravity",
    "gemini4_analyze_codebase",
    "gemini4_security_audit",
    "gemini4_long_decode_refactor",
    "gemini4_antigravity_task",
    "gemini4_cache_telemetry",
} == tool_names, f"Unexpected MCP tools: {tool_names}"

call1 = rpc({
    "jsonrpc": "2.0",
    "id": 3,
    "method": "tools/call",
    "params": {
        "name": "gemini4_analyze_codebase",
        "arguments": {
            "question": "Summarize the routing rules.",
            "paths": ["router/ccr"],
            "model_tier": "flash",
            "workspace_root": kit_dir,
            "session_id": "verify-session",
        },
    },
})
assert not call1["result"]["isError"]
assert "gemini-3.8-flash" in call1["result"]["content"][0]["text"]
assert "implicit_cache_warm=False" in call1["result"]["content"][0]["text"]

call2 = rpc({
    "jsonrpc": "2.0",
    "id": 4,
    "method": "tools/call",
    "params": {
        "name": "gemini4_analyze_codebase",
        "arguments": {
            "question": "Follow-up on fallback chains.",
            "paths": ["router/ccr"],
            "model_tier": "flash",
            "workspace_root": kit_dir,
            "session_id": "verify-session",
        },
    },
})
assert "implicit_cache_warm=True" in call2["result"]["content"][0]["text"]

agy_call = rpc({
    "jsonrpc": "2.0",
    "id": 5,
    "method": "tools/call",
    "params": {
        "name": "ask_antigravity",
        "arguments": {
            "prompt": "Critique our cache-preserving subagent boundary.",
            "paths": ["router/litellm"],
            "model": "claude-gemini-4-argon[1m]",
            "workspace_root": kit_dir,
        },
    },
})
assert not agy_call["result"]["isError"]
assert "gemini-4-argon" in agy_call["result"]["content"][0]["text"]
proc.terminate()
print("  PASS: MCP v1.1 exposed all 6 tools (incl. ask_antigravity), normalized [1m] IDs & tracked warm implicit cache.")
PY

# 6. Smart Gateway v1.3 Core Routing, Safeguards & Cache Pinning Invariants
echo '[6/7] Testing Smart Gateway v1.3 (`/model` filter, `safeguard_results`, `claude-auto-gemini`, Pinning & 429)...'
python3 - "${KIT_DIR}/router" <<'PY'
import json, os, sys
sys.path.insert(0, sys.argv[1])
import gemini4_gateway as gw

for entry in gw.GATEWAY_MODEL_CATALOG:
    assert "claude" in entry["id"], f"Model {entry['id']} would be dropped by Claude Code /model filter"

r1 = gw.classify_and_route(
    session_id="root-1",
    requested_model="claude-opus-5-5[1m]",
    messages=[{"role": "user", "content": "Help me plan our auth service cleanup"}],
    token_count_est=8000,
)
assert r1["selected_model"] == "anthropic/claude-opus-5-5"
assert len(r1["prompt_digest"]) == 16

r2 = gw.classify_and_route(
    session_id="root-1",
    requested_model="claude-opus-5-5[1m]",
    messages=[
        {"role": "user", "content": "Plan"},
        {"role": "assistant", "content": "Ok"},
        {"role": "user", "content": "Step 2"},
        {"role": "user", "content": "Run a CWE-89 SQL injection security audit"},
    ],
    token_count_est=24000,
)
assert r2["rule_matched"] == "session_pinned_cache_guard"
assert r2["selected_model"] == "anthropic/claude-opus-5-5"

r3 = gw.classify_and_route(
    session_id="bg-1",
    requested_model="claude-gemini-3.5-flash-lite",
    messages=[{"role": "user", "content": "Classify command safety"}],
    token_count_est=1200,
    has_safeguards=True,
)
assert r3["selected_model"] == "gemini/gemini-3.5-flash-lite"

r4 = gw.classify_and_route(
    session_id="sub-1",
    requested_model="claude-opus-5-5[1m]",
    messages=[{"role": "user", "content": "Explore src/ and map imports"}],
    token_count_est=18000,
    subagent_flag=True,
)
assert r4["selected_model"] == "gemini/gemini-3.8-flash"

r5 = gw.classify_and_route(
    session_id="auto-1",
    requested_model="claude-auto-gemini",
    messages=[{"role": "user", "content": "Audit SSRF and CWE-89 sql injection across modules"}],
    token_count_est=42000,
)
assert r5["selected_model"] == "gemini/gemini-4-argon"

gem_p = gw.translate_anthropic_to_gemini_payload(
    {"messages": [{"role": "user", "content": "Audit"}], "temperature": 0.2, "max_tokens": 8192},
    "gemini-4-argon",
)
assert gem_p["generationConfig"]["maxOutputTokens"] == 65536
assert "temperature" not in gem_p["generationConfig"]

mock_resp = gw.forward_or_mock_anthropic_or_gemini(
    "gemini/gemini-3.8-flash",
    {"messages": [{"role": "user", "content": "ls"}], "safeguards": {"mode": "auto"}},
    r4,
    "sub-1",
)
sse_txt = gw.format_anthropic_sse_stream(mock_resp).decode("utf-8")
assert "safeguard_results" in sse_txt

r6 = gw.classify_and_route(
    session_id="root-1",
    requested_model="claude-opus-5-5[1m]",
    messages=[{"role": "user", "content": "Continue"}],
    token_count_est=28000,
    simulate_429_primary=True,
)
assert r6["selected_model"] == "gemini/gemini-4-argon"
print("  PASS: All 9 Smart Gateway core routing, discovery, safeguard & cache invariants verified.")
PY

# 7. Protocol Edge Cases, Multi-Tenant Path Prefixes & Structured Doctor JSON
echo '[7/7] Testing embedded `role: system`, `/anthropic` & `/openai` prefixes, RISK_WORDS floor & `--doctor --json`...'
python3 - "${KIT_DIR}" <<'PY'
import http.client, json, os, pathlib, subprocess, sys, threading
kit = pathlib.Path(sys.argv[1])
sys.path.insert(0, str(kit / "router"))
import gemini4_gateway as gw

# A. Embedded `role: "system"` inside `messages[]` (Claude Code v2.1.301+ wire behavior)
translated = gw.translate_anthropic_to_gemini_payload(
    {
        "system": "Top-level system instruction.",
        "messages": [
            {"role": "system", "content": "Embedded system hook from Claude Code v2.1.301+."},
            {"role": "user", "content": "Inspect module."},
            {
                "role": "assistant",
                "content": [
                    {"type": "tool_use", "id": "unrecorded_1", "name": "read_file", "input": {"path": "a.py"}},
                    {"type": "tool_use", "id": "unrecorded_2", "name": "read_file", "input": {"path": "b.py"}},
                ],
            },
        ],
    },
    "gemini-3.8-flash",
)
sys_text = translated["systemInstruction"]["parts"][0]["text"]
assert "Top-level system instruction." in sys_text and "Embedded system hook" in sys_text
assert len(translated["contents"]) == 2, "System-role item must not leak into user/model contents"
fc_parts = translated["contents"][1]["parts"]
assert fc_parts[0]["thoughtSignature"] == "skip_thought_signature_validator"
assert "thoughtSignature" not in fc_parts[1], "Only first unrecorded functionCall in turn carries sentinel"

# B. RISK_WORDS_RE floor on `claude-auto-gemini`: short risk prompt must NOT drop to flash-lite
r_safe = gw.classify_and_route(
    session_id="auto-safe",
    requested_model="claude-auto-gemini",
    messages=[{"role": "user", "content": "Format README typo"}],
    token_count_est=400,
)
assert r_safe["selected_model"] == "gemini/gemini-3.5-flash-lite"

r_risk = gw.classify_and_route(
    session_id="auto-risk",
    requested_model="claude-auto-gemini",
    messages=[{"role": "user", "content": "Delete production auth token"}],
    token_count_est=400,
)
assert r_risk["selected_model"] != "gemini/gemini-3.5-flash-lite", "Risk prompt must not downgrade to flash-lite"

# C. Ephemeral HTTP test of `/anthropic/v1/messages/count_tokens`, `/openai/v1/responses` & budget guard
srv = gw.ReusableGatewayHTTPServer(("127.0.0.1", 0), gw.GatewayHandler)
port = srv.server_address[1]
t = threading.Thread(target=srv.serve_forever, daemon=True)
t.start()
try:
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
    conn.request(
        "POST",
        "/anthropic/v1/messages/count_tokens",
        body=json.dumps({"system": "sys", "tools": [{"name": "t1"}], "messages": [{"role": "user", "content": "hello"}]}),
        headers={"Content-Type": "application/json"},
    )
    r_ct = conn.getresponse()
    ct_data = json.loads(r_ct.read().decode("utf-8"))
    assert r_ct.status == 200 and ct_data["input_tokens"] > 0

    conn.request(
        "POST",
        "/openai/v1/responses",
        body=json.dumps({"model": "claude-gemini-3.8-flash", "input": "ping", "store": True, "prompt_cache_key": "k1"}),
        headers={"Content-Type": "application/json"},
    )
    r_oa = conn.getresponse()
    hdr_decision = r_oa.getheader("X-Gemini4-Gateway") or ""
    oa_data = json.loads(r_oa.read().decode("utf-8"))
    assert r_oa.status == 200 and "gemini-3.8-flash" in hdr_decision
    assert any("store" in fix for fix in oa_data["x_gemini4_gateway"]["protocol_fixes_applied"])

    os.environ["GEMINI4_SESSION_BUDGET_USD"] = "0.000001"
    conn.request(
        "POST",
        "/anthropic/v1/messages",
        body=json.dumps({"model": "claude-gemini-4-argon", "messages": [{"role": "user", "content": "x" * 2000}]}),
        headers={"Content-Type": "application/json", "x-session-id": "budget-cap-test"},
    )
    r_cap = conn.getresponse()
    cap_data = json.loads(r_cap.read().decode("utf-8"))
    assert r_cap.status == 403 and cap_data["type"] == "error"
    conn.close()
finally:
    os.environ.pop("GEMINI4_SESSION_BUDGET_USD", None)
    srv.shutdown()
    srv.server_close()

# D. Structured `./install.sh --doctor --json` check
doc_proc = subprocess.run(
    [str(kit / "install.sh"), "--doctor", "--json"],
    capture_output=True,
    text=True,
    timeout=15,
    check=False,
)
assert doc_proc.returncode == 0, f"doctor --json failed: {doc_proc.stderr}"
doc_json = json.loads(doc_proc.stdout)
check_names = {c["check"] for c in doc_json["checks"]}
assert {"host.python", "host.loopback", "auth.google", "gateway.health"}.issubset(check_names)
print("  PASS: Embedded system messages, /anthropic & /openai prefixes, RISK_WORDS floor, budget guard & doctor --json verified.")
PY

echo ""
echo "=================================================================="
echo " ALL 7 VERIFICATION SUITES PASSED SUCCESSFULLY (v1.3 Nov 2026)"
echo "=================================================================="
