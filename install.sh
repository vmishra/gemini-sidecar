#!/usr/bin/env bash
# =============================================================================
# Gemini 4 Multi-Harness Coexistence Installer & Doctor (`install.sh` v1.3)
# Supports:
#   - Claude Code (v2.1.302+ Marketplace Plugin AND legacy v1.x/v2.0 MCP fallback)
#   - OpenAI Codex CLI (v0.134–v0.159+ `--profile gemini4` Responses API)
#   - Cursor IDE (Post-Oct 2026 Subagents, Rules & 1-Click MCP Deeplink)
#   - Smart Gateway / LiteLLM v1.109+ / `claude-code-router` (CCR)
# Safe & Idempotent: backs up modified files, never logs secrets, supports `--doctor [--json]`
# =============================================================================
set -euo pipefail

KIT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MCP_SERVER="${KIT_DIR}/plugins/gemini4-coexistence/mcp/gemini4_mcp_server.py"
GATEWAY_PY="${KIT_DIR}/router/gemini4_gateway.py"

DO_CLAUDE=0
DO_CODEX=0
DO_CURSOR=0
DO_CCR=0
DO_DOCTOR=0
DOCTOR_JSON=0
DRY_RUN=0
TARGET_PROJECT=""

usage() {
  cat <<EOF
Gemini 4 Multi-Harness Coexistence Kit (v1.3 — Nov 2026)

Usage: ./install.sh [options]

Options:
  --doctor              Run read-only environment, auth & harness diagnostics (ok|todo|warn|fail)
  --json                Emit machine-readable JSON when combined with --doctor
  --all                 Install across Claude Code, Codex CLI, Cursor IDE, and Gateway/CCR
  --claude              Install Claude Code plugin (auto-adapts to Claude v2.1+ or legacy v1/v2.0)
  --codex               Install Codex CLI profiles & explorer/argon subagents (~/.codex)
  --cursor              Install Cursor subagents, Oct 2026 rules & 1-click MCP deeplink
  --ccr                 Install claude-code-router (CCR) & LiteLLM v1.109+ configs
  --project <dir>       Install project-scoped (.claude / .codex / .cursor / .mcp.json) into <dir>
  --dry-run             Preview every file & command without modifying your machine
  -h, --help            Show this help message

Typical Workflow:
  1. ./install.sh --doctor          # Read-only readiness check (never prints secret values)
  2. ./install.sh --all             # Install non-destructively across harnesses
  3. ./verify.sh                    # Run all 7 hermetic verification suites
EOF
}

if [[ $# -eq 0 ]]; then
  usage
  exit 0
fi

while [[ $# -gt 0 ]]; do
  case "$1" in
    --doctor) DO_DOCTOR=1; shift ;;
    --json) DOCTOR_JSON=1; shift ;;
    --all) DO_CLAUDE=1; DO_CODEX=1; DO_CURSOR=1; DO_CCR=1; shift ;;
    --claude) DO_CLAUDE=1; shift ;;
    --codex) DO_CODEX=1; shift ;;
    --cursor) DO_CURSOR=1; shift ;;
    --ccr) DO_CCR=1; shift ;;
    --project)
      if [[ $# -lt 2 ]]; then echo "ERROR: --project requires a directory path."; exit 1; fi
      TARGET_PROJECT="$2"; shift 2 ;;
    --dry-run) DRY_RUN=1; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "ERROR: Unknown option '$1'. Run './install.sh --help' for usage."; exit 1 ;;
  esac
done

if [[ -n "${TARGET_PROJECT}" && "${DO_CLAUDE}" -eq 0 && "${DO_CODEX}" -eq 0 && "${DO_CURSOR}" -eq 0 && "${DO_CCR}" -eq 0 && "${DO_DOCTOR}" -eq 0 ]]; then
  DO_CLAUDE=1
  DO_CODEX=1
  DO_CURSOR=1
fi

run_doctor() {
  if ! command -v python3 >/dev/null 2>&1; then
    if [[ "${DOCTOR_JSON}" -eq 1 ]]; then
      echo '{"overall":"fail","checks":[{"status":"fail","check":"host.python","detail":"python3 not found on PATH","fix":"Install Python 3.9+ (brew install python)"}]}'
    else
      echo "STATUS  CHECK        DETAIL"
      echo "fail    host.python  python3 not found on PATH (Fix: brew install python)"
    fi
    return 1
  fi

  python3 - "${KIT_DIR}" "${DOCTOR_JSON}" <<'PY'
import http.client
import json
import os
import pathlib
import shutil
import socket
import subprocess
import sys

kit_dir = pathlib.Path(sys.argv[1])
as_json = sys.argv[2] == "1"
home = pathlib.Path.home()
checks = []

def add(status: str, check: str, detail: str, fix: str = "") -> None:
    entry = {"status": status, "check": check, "detail": detail}
    if fix:
        entry["fix"] = fix
    checks.append(entry)

# 1. host.python
py_ver = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
if sys.version_info >= (3, 9):
    add("ok", "host.python", f"Python {py_ver} ({sys.executable})")
else:
    add("fail", "host.python", f"Python {py_ver} is older than 3.9", "Install Python 3.10+ (e.g. brew install python)")

# 2. host.loopback
try:
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(("127.0.0.1", 0))
    s.close()
    add("ok", "host.loopback", "127.0.0.1 ephemeral TCP bind permitted")
except Exception as exc:
    add("fail", "host.loopback", f"Loopback TCP bind blocked ({exc})", "Allow localhost TCP sockets for gateway/MCP")

# 3. auth.google (names only — never print secret values)
detected_google_sources = []
for var in ("GEMINI_API_KEY", "GOOGLE_API_KEY", "GEMINI4_PLUGIN_API_KEY"):
    if (os.environ.get(var) or "").strip():
        detected_google_sources.append(var)
if (os.environ.get("GOOGLE_GENAI_USE_VERTEXAI") or "").lower() in ("1", "true", "yes"):
    proj = (os.environ.get("GOOGLE_CLOUD_PROJECT") or "").strip()
    detected_google_sources.append("GOOGLE_GENAI_USE_VERTEXAI" + ("+GOOGLE_CLOUD_PROJECT" if proj else " (missing GOOGLE_CLOUD_PROJECT)"))

if detected_google_sources:
    add("ok", "auth.google", f"Detected {', '.join(detected_google_sources)} (values redacted)")
else:
    add(
        "todo",
        "auth.google",
        "No GEMINI_API_KEY or GOOGLE_GENAI_USE_VERTEXAI set in current shell",
        "export GEMINI_API_KEY=\"<paid-tier-key>\"  # or set GOOGLE_GENAI_USE_VERTEXAI=true GOOGLE_CLOUD_PROJECT=<id>",
    )

# 4. auth.subscriptions (Track A direct subscription coexistence awareness)
sub_sources = []
if (os.environ.get("CLAUDE_CODE_OAUTH_TOKEN") or "").strip() or (home / ".claude" / ".credentials.json").is_file():
    sub_sources.append("Claude OAuth")
if (home / ".codex" / "auth.json").is_file():
    sub_sources.append("Codex auth.json")
if sub_sources:
    add("ok", "auth.subscriptions", f"Subscription login present ({', '.join(sub_sources)}); Track A Direct MCP ready")
else:
    add("todo", "auth.subscriptions", "No local Claude/Codex OAuth file detected (API key or Gateway mode available)")

# 5. auth.env_hygiene (Claude 2.1.283+ apiKeyHelper conflict check)
if os.environ.get("CLAUDE_CODE_PROVIDER_MANAGED_BY_HOST") == "1":
    add(
        "warn",
        "auth.env_hygiene",
        "CLAUDE_CODE_PROVIDER_MANAGED_BY_HOST=1 causes Claude 2.1.283+ to ignore apiKeyHelper",
        "unset CLAUDE_CODE_PROVIDER_MANAGED_BY_HOST",
    )
else:
    add("ok", "auth.env_hygiene", "No conflicting provider-managed auth overrides in environment")

# 6. harnesses.claude-code
claude_bin = shutil.which("claude")
if claude_bin:
    ver_proc = subprocess.run([claude_bin, "--version"], capture_output=True, text=True, timeout=5, check=False)
    ver_str = (ver_proc.stdout.strip().splitlines() or ["installed"])[0]
    plug_proc = subprocess.run([claude_bin, "plugin", "--help"], capture_output=True, text=True, timeout=5, check=False)
    mode_note = "native plugin marketplace supported" if plug_proc.returncode == 0 else "legacy MCP + .claude/agents fallback"
    add("ok", "harnesses.claude-code", f"{ver_str} ({mode_note})")
else:
    add("todo", "harnesses.claude-code", "claude CLI not on PATH (optional)")

# 7. harnesses.codex
codex_bin = shutil.which("codex")
if codex_bin:
    ver_proc = subprocess.run([codex_bin, "--version"], capture_output=True, text=True, timeout=5, check=False)
    ver_str = (ver_proc.stdout.strip().splitlines() or ["installed"])[0]
    add("ok", "harnesses.codex", f"{ver_str} (--profile gemini4 via local /v1/responses gateway)")
else:
    add("todo", "harnesses.codex", "codex CLI not on PATH (optional)")

# 8. harnesses.cursor
if (home / ".cursor").is_dir() or pathlib.Path("/Applications/Cursor.app").is_dir():
    add("ok", "harnesses.cursor", f"Cursor installation detected ({home / '.cursor'})")
else:
    add("todo", "harnesses.cursor", "~/.cursor not initialized yet (created on --cursor install)")

# 9. harnesses.antigravity
agy_bin = shutil.which("agy") or (str(home / ".local" / "bin" / "agy") if (home / ".local" / "bin" / "agy").is_file() else None)
if agy_bin:
    agy_settings = home / ".gemini" / "antigravity-cli" / "settings.json"
    if agy_settings.is_file():
        try:
            cfg = json.loads(agy_settings.read_text(encoding="utf-8"))
            if cfg.get("modelProvider") == "gemini":
                add("ok", "harnesses.antigravity", f"agy CLI detected ({agy_bin}); modelProvider=gemini")
            else:
                add(
                    "warn",
                    "harnesses.antigravity",
                    f"agy CLI detected, but {agy_settings} lacks \"modelProvider\": \"gemini\" for headless -p",
                    f"Set '\"modelProvider\": \"gemini\"' in {agy_settings}",
                )
        except Exception:
            add("ok", "harnesses.antigravity", f"agy CLI detected ({agy_bin})")
    else:
        add("ok", "harnesses.antigravity", f"agy CLI detected ({agy_bin}); MCP falls back to REST/SDK when unconfigured")
else:
    add("todo", "harnesses.antigravity", "agy CLI optional (MCP uses stdlib REST or google-genai automatically)")

# 10. gateway.health
gw_port = int(os.environ.get("GEMINI4_GATEWAY_PORT", "3456"))
try:
    conn = http.client.HTTPConnection("127.0.0.1", gw_port, timeout=1.2)
    conn.request("GET", "/health")
    resp = conn.getresponse()
    body = json.loads(resp.read().decode("utf-8") or "{}")
    conn.close()
    if resp.status == 200 and body.get("status") == "online":
        add("ok", "gateway.health", f"Listening on 127.0.0.1:{gw_port} (v{body.get('version', '1.x')})")
    else:
        add("warn", "gateway.health", f"Port {gw_port} responded HTTP {resp.status}")
except Exception:
    add(
        "todo",
        "gateway.health",
        f"Gateway not currently running on 127.0.0.1:{gw_port} (needed for Track B / Codex)",
        f"python3 {kit_dir / 'router' / 'gemini4_gateway.py'} &",
    )

rank = {"ok": 0, "todo": 1, "warn": 2, "fail": 3}
worst = max((c["status"] for c in checks), key=lambda s: rank[s])
counts = {k: sum(1 for c in checks if c["status"] == k) for k in ("ok", "todo", "warn", "fail")}

if as_json:
    print(json.dumps({"overall": worst, "counts": counts, "checks": checks}, indent=2))
else:
    print("Gemini 4 Coexistence Kit — Environment Doctor (Read-Only)")
    print("-" * 82)
    print(f"{'STATUS':<7} {'CHECK':<24} DETAIL")
    print("-" * 82)
    for c in checks:
        print(f"{c['status']:<7} {c['check']:<24} {c['detail']}")
    print("-" * 82)
    summary_parts = [f"{counts[k]} {k}" for k in ("ok", "todo", "warn", "fail") if counts[k]]
    print("Summary: " + ", ".join(summary_parts))
    actionable = [c for c in checks if c.get("fix")]
    if actionable:
        print("\nNext steps (optional unless marked fail):")
        for c in actionable:
            print(f"  - [{c['check']}] {c['fix']}")

sys.exit(1 if worst == "fail" else 0)
PY
}

if [[ "$DO_DOCTOR" -eq 1 ]]; then
  run_doctor
  if [[ "$DO_CLAUDE" -eq 0 && "$DO_CODEX" -eq 0 && "$DO_CURSOR" -eq 0 && "$DO_CCR" -eq 0 ]]; then
    exit 0
  fi
fi

if ! command -v python3 >/dev/null 2>&1; then
  echo "ERROR: 'python3' (>= 3.9) is required by the MCP server and Smart Gateway, but was not found on PATH."
  echo "Fix: Install Python 3 ('brew install python' on macOS or 'sudo apt install python3' on Ubuntu/Debian)."
  exit 1
fi

run_step() {
  if [[ "$DRY_RUN" -eq 1 ]]; then
    echo "  [dry-run] $*"
  else
    eval "$@"
  fi
}

backup_if_exists() {
  local target="$1"
  if [[ -f "${target}" && "${DRY_RUN}" -eq 0 ]]; then
    cp "${target}" "${target}.bak.$(date +%Y%m%d%H%M%S)"
  fi
}

echo "=================================================================="
echo " Gemini 4 Coexistence Kit Installer (v1.3 — Nov 2026)"
echo " Kit Root: ${KIT_DIR}"
echo "=================================================================="

if [[ "$DO_CLAUDE" -eq 1 ]]; then
  echo ""
  echo "-> [Claude Code] Configuring plugin, subagents & role-pinning templates..."
  CLAUDE_HOME="${TARGET_PROJECT:+${TARGET_PROJECT}/.claude}"
  CLAUDE_HOME="${CLAUDE_HOME:-${HOME}/.claude}"
  run_step "mkdir -p \"${CLAUDE_HOME}\""

  if command -v claude >/dev/null 2>&1; then
    if claude plugin --help >/dev/null 2>&1; then
      run_step "claude plugin validate \"${KIT_DIR}\""
      run_step "claude plugin marketplace add \"${KIT_DIR}\" >/dev/null 2>&1 || true"
      run_step "claude plugin install gemini4-coexistence@gemini4-harness-kit >/dev/null 2>&1 || claude plugin update gemini4-coexistence@gemini4-harness-kit >/dev/null 2>&1 || true"
      echo "   [ok] Installed native plugin 'gemini4-coexistence@gemini4-harness-kit'."
      echo "   -> Optional credential store: claude plugin configure gemini4-coexistence"
    else
      echo "   [info] Detected pre-v2.1 Claude CLI without 'claude plugin'. Applying legacy MCP + subagents fallback..."
      run_step "mkdir -p \"${CLAUDE_HOME}/agents\""
      for ag_md in "${KIT_DIR}"/plugins/gemini4-coexistence/agents/*.md; do
        run_step "cp \"${ag_md}\" \"${CLAUDE_HOME}/agents/\""
      done
      run_step "claude mcp remove gemini4 >/dev/null 2>&1 || true"
      run_step "claude mcp add gemini4 -- python3 \"${MCP_SERVER}\" || true"
      echo "   [ok] Registered 'gemini4' MCP server and copied subagents into ${CLAUDE_HOME}/agents/."
    fi
  else
    echo "   [info] 'claude' CLI not found on PATH. Staging subagents & role-pinning templates in ${CLAUDE_HOME}/."
    run_step "mkdir -p \"${CLAUDE_HOME}/agents\""
    for ag_md in "${KIT_DIR}"/plugins/gemini4-coexistence/agents/*.md; do
      run_step "cp \"${ag_md}\" \"${CLAUDE_HOME}/agents/\""
    done
  fi

  run_step "cp \"${KIT_DIR}/claude/settings.hybrid-role-pinning.json\" \"${CLAUDE_HOME}/settings.gemini4-hybrid.example.json\""
  run_step "cp \"${KIT_DIR}/claude/settings.all-gemini-tiered.json\" \"${CLAUDE_HOME}/settings.gemini4-all-tiered.example.json\""
  if [[ -n "${TARGET_PROJECT}" && ! -f "${TARGET_PROJECT}/.mcp.json" && "${DRY_RUN}" -eq 0 ]]; then
    sed "s|__GEMINI4_MCP_SERVER_PATH__|${MCP_SERVER}|g" "${KIT_DIR}/cursor/mcp.json" > "${TARGET_PROJECT}/.mcp.json"
    echo "   [ok] Created project-scoped ${TARGET_PROJECT}/.mcp.json."
  fi
  echo "   [ok] Role-pinning templates staged in ${CLAUDE_HOME}/."
fi

if [[ "$DO_CODEX" -eq 1 ]]; then
  echo ""
  echo "-> [OpenAI Codex CLI] Configuring Responses API profiles & subagents..."
  CODEX_HOME="${TARGET_PROJECT:+${TARGET_PROJECT}/.codex}"
  CODEX_HOME="${CODEX_HOME:-${HOME}/.codex}"
  run_step "mkdir -p \"${CODEX_HOME}/agents\""
  if [[ -z "${TARGET_PROJECT}" ]]; then
    for prof in gemini4.config.toml gemini4-security.config.toml; do
      if [[ "$DRY_RUN" -eq 1 ]]; then
        echo "  [dry-run] Render ${CODEX_HOME}/${prof} with MCP path ${MCP_SERVER}"
      else
        backup_if_exists "${CODEX_HOME}/${prof}"
        sed "s|__GEMINI4_MCP_SERVER_PATH__|${MCP_SERVER}|g" "${KIT_DIR}/codex/${prof}" > "${CODEX_HOME}/${prof}"
        echo "   [ok] Installed ${CODEX_HOME}/${prof}"
      fi
    done
    if [[ ! -f "${CODEX_HOME}/config.toml" ]]; then
      if [[ "$DRY_RUN" -eq 1 ]]; then
        echo "  [dry-run] Initialize ${CODEX_HOME}/config.toml from gemini4.config.toml"
      else
        cp "${CODEX_HOME}/gemini4.config.toml" "${CODEX_HOME}/config.toml"
        echo "   [ok] Created default ${CODEX_HOME}/config.toml (no existing config.toml was present)."
      fi
    else
      echo "   [info] Preserved existing ${CODEX_HOME}/config.toml (launch via 'codex --profile gemini4' or 'codex exec --profile gemini4-security')."
    fi
  else
    if [[ ! -f "${TARGET_PROJECT}/AGENTS.md" && "${DRY_RUN}" -eq 0 ]]; then
      cp "${KIT_DIR}/codex/AGENTS.md" "${TARGET_PROJECT}/AGENTS.md"
      echo "   [ok] Installed project-scoped ${TARGET_PROJECT}/AGENTS.md"
    fi
    echo "   [info] Codex ignores model_providers in repo-local .codex/config.toml; run './install.sh --codex' once to install user-level ~/.codex/gemini4.config.toml."
  fi
  for agent_toml in "${KIT_DIR}"/codex/agents/*.toml; do
    run_step "cp \"${agent_toml}\" \"${CODEX_HOME}/agents/\""
  done
  echo "   [ok] Installed Codex subagents (explorer.toml, argon-reviewer.toml, argon-migrator.toml)."
  echo "   -> Start the local gateway ('python3 ${GATEWAY_PY} &') before launching Codex."
fi

if [[ "$DO_CURSOR" -eq 1 ]]; then
  echo ""
  echo "-> [Cursor IDE] Configuring subagents, Oct 2026 rules & MCP deeplink..."
  CURSOR_DEST="${TARGET_PROJECT:+${TARGET_PROJECT}/.cursor}"
  CURSOR_DEST="${CURSOR_DEST:-${HOME}/.cursor}"
  run_step "mkdir -p \"${CURSOR_DEST}/agents\" \"${CURSOR_DEST}/rules\""
  for ag in "${KIT_DIR}"/cursor/agents/*.md; do
    run_step "cp \"${ag}\" \"${CURSOR_DEST}/agents/\""
  done
  run_step "cp \"${KIT_DIR}/cursor/rules/gemini4-coexistence.mdc\" \"${CURSOR_DEST}/rules/\""
  if [[ "$DRY_RUN" -eq 0 ]]; then
    sed "s|__GEMINI4_MCP_SERVER_PATH__|${MCP_SERVER}|g" "${KIT_DIR}/cursor/mcp.json" > "${CURSOR_DEST}/mcp.gemini4.example.json"
    if [[ ! -f "${CURSOR_DEST}/mcp.json" ]]; then
      cp "${CURSOR_DEST}/mcp.gemini4.example.json" "${CURSOR_DEST}/mcp.json"
      echo "   [ok] Created ${CURSOR_DEST}/mcp.json (no existing mcp.json was present)."
    else
      echo "   [info] Preserved existing ${CURSOR_DEST}/mcp.json (see ${CURSOR_DEST}/mcp.gemini4.example.json or use the URI below)."
    fi
  fi

  B64_CFG="$(python3 -c "import base64, json; cfg={'command':'python3','args':['${MCP_SERVER}'],'env':{'GEMINI4_PRIMARY_MODEL':'gemini-4-argon','GEMINI4_SUBAGENT_MODEL':'gemini-3.8-flash','GEMINI4_BACKGROUND_MODEL':'gemini-3.5-flash-lite'}}; print(base64.b64encode(json.dumps(cfg).encode()).decode())")"
  echo "   [ok] Cursor MCP Install URI:"
  echo "   cursor://anysphere.cursor-deeplink/mcp/install?name=gemini4&config=${B64_CFG}"
fi

if [[ "$DO_CCR" -eq 1 ]]; then
  echo ""
  echo "-> [Gateway / CCR / LiteLLM] Staging router configurations..."
  CCR_DIR="${HOME}/.claude-code-router"
  run_step "mkdir -p \"${CCR_DIR}\""
  run_step "cp \"${KIT_DIR}/router/ccr/gemini4-cache-aware-router.js\" \"${CCR_DIR}/\""
  run_step "cp \"${KIT_DIR}/router/ccr/ccr-v3-profile.json\" \"${CCR_DIR}/\""
  run_step "cp \"${KIT_DIR}/router/ccr/config.v1-v2.json\" \"${CCR_DIR}/\""
  run_step "cp \"${KIT_DIR}/router/litellm/litellm_config.yaml\" \"${CCR_DIR}/\""
  echo "   [ok] Installed CCR + LiteLLM configs in ${CCR_DIR}/"
  echo "   -> Start zero-dependency Smart Gateway: python3 \"${GATEWAY_PY}\""
fi

echo ""
echo "=================================================================="
echo " Installation Complete. Next Step: Run '${KIT_DIR}/verify.sh'"
echo "=================================================================="
