#!/usr/bin/env bash
# Installer for gemini4-harness-kit.
#
#   ./install.sh --doctor [--json]       read-only readiness check (never prints secret values)
#   ./install.sh --claude                install the Claude Code plugin (/gemini:* commands)
#   ./install.sh --codex                 add the gemini4 MCP server to ~/.codex/config.toml
#   ./install.sh --cursor                add the gemini4 MCP server to ~/.cursor/mcp.json and install subagents
#   ./install.sh --gateway-profile hybrid|all-gemini [--project DIR]
#                                        write the Claude Code gateway profile to DIR/.claude/settings.local.json
#   ./install.sh --all                   --claude, --codex and --cursor for whichever harnesses are installed
#   --dry-run                            print what would change without changing anything
#
# Every file that is modified is first copied to <file>.bak.<timestamp>.

set -euo pipefail

KIT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MCP_SERVER="${KIT_DIR}/plugins/gemini/mcp/gemini4_mcp_server.py"
STAMP="$(date +%Y%m%d-%H%M%S)"
DRY_RUN=0
DO_DOCTOR=0 DOCTOR_JSON=0 DO_CLAUDE=0 DO_CODEX=0 DO_CURSOR=0 DO_ALL=0
PROFILE="" PROJECT_DIR="${PWD}"

usage() { sed -n '2,13p' "$0" | sed 's/^# \{0,1\}//'; }

while [[ $# -gt 0 ]]; do
  case "$1" in
    --doctor) DO_DOCTOR=1 ;;
    --json) DOCTOR_JSON=1 ;;
    --claude) DO_CLAUDE=1 ;;
    --codex) DO_CODEX=1 ;;
    --cursor) DO_CURSOR=1 ;;
    --all) DO_ALL=1 ;;
    --gateway-profile) PROFILE="${2:-}"; shift ;;
    --project) PROJECT_DIR="${2:-}"; shift ;;
    --dry-run) DRY_RUN=1 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown option: $1" >&2; usage >&2; exit 2 ;;
  esac
  shift
done

if [[ $DO_DOCTOR -eq 0 && $DO_CLAUDE -eq 0 && $DO_CODEX -eq 0 && $DO_CURSOR -eq 0 && $DO_ALL -eq 0 && -z "$PROFILE" ]]; then
  usage; exit 0
fi

have() { command -v "$1" >/dev/null 2>&1; }

# Run a command, or print it under --dry-run. Arguments are passed through unchanged (no eval).
run() {
  if [[ $DRY_RUN -eq 1 ]]; then
    printf '   [dry-run]'; printf ' %q' "$@"; printf '\n'
  else
    "$@"
  fi
}

backup() {
  local f="$1"
  if [[ -e "$f" ]]; then run cp -p "$f" "${f}.bak.${STAMP}"; fi
}

# --------------------------------------------------------------------------- doctor
doctor() {
  python3 - "$KIT_DIR" "$DOCTOR_JSON" <<'PY'
import json, os, shutil, socket, stat, subprocess, sys
from pathlib import Path

kit, as_json = Path(sys.argv[1]), sys.argv[2] == "1"
checks = []

def add(name, status, detail):
    checks.append({"check": name, "status": status, "detail": detail})

v = sys.version_info
add("python", "ok" if v >= (3, 9) else "fail", f"{v.major}.{v.minor}.{v.micro} (3.9+ required)")

for tool, why in (("claude", "Claude Code"), ("codex", "Codex CLI"), ("cursor", "Cursor CLI"),
                  ("agy", "Antigravity CLI (optional)"), ("gcloud", "needed for Vertex AI"), ("git", "needed for /gemini:review")):
    path = shutil.which(tool)
    version = ""
    if path and tool in ("claude", "codex", "agy"):
        try:
            version = subprocess.run([path, "--version"], capture_output=True, text=True, timeout=10).stdout.strip().splitlines()[0]
        except (OSError, subprocess.SubprocessError, IndexError):
            version = "version unknown"
    add(tool, "ok" if path else "info", f"{why}: {version or path or 'not found'}")

def is_set(name):
    val = (os.environ.get(name) or "").strip()
    return bool(val) and not val.startswith("${")

api_key = is_set("GEMINI_API_KEY") or is_set("GOOGLE_API_KEY")
vertex = (os.environ.get("GOOGLE_GENAI_USE_VERTEXAI") or "").lower() in ("1", "true", "yes")
if api_key:
    add("credentials", "ok", "Gemini API key variable is set (value not shown)")
elif vertex and is_set("GOOGLE_CLOUD_PROJECT"):
    add("credentials", "ok", "Vertex AI enabled; GOOGLE_CLOUD_PROJECT is set")
elif vertex:
    add("credentials", "fail", "GOOGLE_GENAI_USE_VERTEXAI is set but GOOGLE_CLOUD_PROJECT is not")
else:
    add("credentials", "todo", "set GEMINI_API_KEY, or GOOGLE_GENAI_USE_VERTEXAI=true + GOOGLE_CLOUD_PROJECT "
        "(the Claude Code plugin can also store a key via /plugin configure gemini@gemini4-harness-kit)")

try:
    out = subprocess.run([sys.executable, str(kit / "plugins/gemini/mcp/gemini4_mcp_server.py"), "--self-test"],
                         capture_output=True, text=True, timeout=20)
    tools = json.loads(out.stdout)["tools"]
    add("mcp_server", "ok", f"self-test passed, {len(tools)} tools")
except Exception as exc:  # noqa: BLE001
    add("mcp_server", "fail", f"self-test failed: {type(exc).__name__}")

port = int(os.environ.get("GEMINI4_GATEWAY_PORT", "3456"))
with socket.socket() as s:
    s.settimeout(0.5)
    running = s.connect_ex(("127.0.0.1", port)) == 0
add("gateway", "ok" if running else "info", f"127.0.0.1:{port} {'is listening' if running else 'not running (only needed for gateway profiles)'}")

token = Path.home() / ".config" / "gemini4" / "gateway-token"
if token.exists():
    mode = stat.S_IMODE(token.stat().st_mode)
    add("gateway_token", "ok" if mode & 0o077 == 0 else "warn",
        f"{token} mode {oct(mode)}" + ("" if mode & 0o077 == 0 else " (should be 0600)"))
else:
    add("gateway_token", "info", f"{token} not created yet (the gateway creates it on first start)")

for var in ("CLAUDE_CODE_USE_VERTEX", "CLAUDE_CODE_USE_BEDROCK"):
    if (os.environ.get(var) or "") not in ("", "0", "false"):
        add(var.lower(), "warn", f"{var} is set in the environment; the gateway profiles override it to 0 for Claude Code")

if as_json:
    print(json.dumps({"checks": checks}, indent=2))
else:
    width = max(len(c["check"]) for c in checks)
    for c in checks:
        print(f"  [{c['status']:>4}] {c['check']:<{width}}  {c['detail']}")
PY
}

# --------------------------------------------------------------------------- claude
install_claude() {
  echo "Claude Code plugin"
  if ! have claude; then echo "   claude not found; skipping."; return; fi
  run claude plugin marketplace add "$KIT_DIR"
  run claude plugin install gemini@gemini4-harness-kit
  echo "   Done. Restart Claude Code, then try /gemini:status."
  echo "   To store an API key: /plugin configure gemini@gemini4-harness-kit (inside Claude Code)."
}

# --------------------------------------------------------------------------- codex
install_codex() {
  echo "Codex CLI MCP server"
  local cfg="${CODEX_HOME:-$HOME/.codex}/config.toml"
  if [[ -f "$cfg" ]] && grep -q '^\[mcp_servers\.gemini4\]' "$cfg"; then
    echo "   [mcp_servers.gemini4] already present in $cfg; leaving it unchanged."
    return
  fi
  run mkdir -p "$(dirname "$cfg")"
  backup "$cfg"
  if [[ $DRY_RUN -eq 1 ]]; then echo "   [dry-run] append [mcp_servers.gemini4] to $cfg"; return; fi
  python3 - "$cfg" "$MCP_SERVER" "${KIT_DIR}/codex/config.toml.example" <<'PY'
import json, sys
cfg, server, example = sys.argv[1:4]
block = open(example, encoding="utf-8").read()
start = block.index("[mcp_servers.gemini4]")
block = block[start:].replace('"/absolute/path/to/gemini4-harness-kit/plugins/gemini/mcp/gemini4_mcp_server.py"',
                              json.dumps(server))  # JSON string escaping is valid TOML
with open(cfg, "a", encoding="utf-8") as fh:
    fh.write("\n# Added by gemini4-harness-kit install.sh\n" + block)
PY
  echo "   Appended to $cfg. Copy codex/AGENTS.md into a project to guide tool use."
}

# --------------------------------------------------------------------------- cursor
install_cursor() {
  echo "Cursor MCP server and subagents"
  local dir="$HOME/.cursor" cfg="$HOME/.cursor/mcp.json"
  run mkdir -p "$dir/agents"
  backup "$cfg"
  if [[ $DRY_RUN -eq 1 ]]; then
    echo "   [dry-run] merge gemini4 into $cfg"
  else
    python3 - "$cfg" "$MCP_SERVER" "${KIT_DIR}/cursor/mcp.json" <<'PY'
import json, os, sys
cfg, server, template = sys.argv[1:4]
data = {}
if os.path.exists(cfg):
    with open(cfg, encoding="utf-8") as fh:
        text = fh.read().strip()
    data = json.loads(text) if text else {}
entry = json.load(open(template, encoding="utf-8"))["mcpServers"]["gemini4"]
entry["args"] = [server]
data.setdefault("mcpServers", {})["gemini4"] = entry
with open(cfg, "w", encoding="utf-8") as fh:
    json.dump(data, fh, indent=2)
    fh.write("\n")
PY
  fi
  local f dest
  for f in "${KIT_DIR}"/cursor/agents/*.md; do
    dest="$dir/agents/$(basename "$f")"
    backup "$dest"
    run cp "$f" "$dest"
  done
  echo "   Done. For project rules, copy cursor/rules/gemini4-coexistence.mdc to <project>/.cursor/rules/."
}

# --------------------------------------------------------------------------- gateway profile
install_profile() {
  local src
  case "$PROFILE" in
    hybrid) src="${KIT_DIR}/claude/settings.hybrid-role-pinning.json" ;;
    all-gemini) src="${KIT_DIR}/claude/settings.all-gemini-tiered.json" ;;
    *) echo "--gateway-profile must be 'hybrid' or 'all-gemini'" >&2; exit 2 ;;
  esac
  if [[ ! -d "$PROJECT_DIR" ]]; then echo "Project directory not found: $PROJECT_DIR" >&2; exit 2; fi
  local dest="${PROJECT_DIR}/.claude/settings.local.json"
  echo "Claude Code gateway profile ($PROFILE)"
  run mkdir -p "${PROJECT_DIR}/.claude"
  backup "$dest"
  if [[ $DRY_RUN -eq 1 ]]; then
    echo "   [dry-run] merge $(basename "$src") into $dest"
  else
    # Merge rather than replace, so existing permissions and other settings are kept.
    python3 - "$src" "$dest" <<'PY'
import json, os, sys
src, dest = sys.argv[1:3]
profile = json.load(open(src, encoding="utf-8"))
current = {}
if os.path.exists(dest):
    text = open(dest, encoding="utf-8").read().strip()
    current = json.loads(text) if text else {}
env = {**current.get("env", {}), **profile.get("env", {})}
merged = {**current, **profile, "env": env}
with open(dest, "w", encoding="utf-8") as fh:
    json.dump(merged, fh, indent=2)
    fh.write("\n")
PY
    echo "   Merged profile into $dest"
  fi
  echo "   Start the gateway before launching claude: python3 \"${KIT_DIR}/router/gemini4_gateway.py\""
  if [[ "$PROFILE" == "hybrid" ]]; then
    echo "   Hybrid mode forwards Claude models to api.anthropic.com: export ANTHROPIC_UPSTREAM_KEY in the gateway's shell."
  fi
}

# --------------------------------------------------------------------------- main
if [[ $DO_DOCTOR -eq 1 ]]; then doctor; fi
if [[ $DO_ALL -eq 1 ]]; then
  have claude && DO_CLAUDE=1
  have codex && DO_CODEX=1
  { have cursor || [[ -d "$HOME/.cursor" ]]; } && DO_CURSOR=1
fi
if [[ $DO_CLAUDE -eq 1 ]]; then install_claude; fi
if [[ $DO_CODEX -eq 1 ]]; then install_codex; fi
if [[ $DO_CURSOR -eq 1 ]]; then install_cursor; fi
if [[ -n "$PROFILE" ]]; then install_profile; fi
