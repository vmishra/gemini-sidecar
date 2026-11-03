#!/usr/bin/env bash
# Offline verification for gemini-sidecar. Makes no network calls and needs no credentials.
#
#   ./verify.sh
#
# 1. JSON and TOML config files parse; shell scripts pass `bash -n`.
# 2. Plugin and marketplace manifests validate with `claude plugin validate` (skipped if claude is absent).
# 3. Every skill's allowed-tools only references tools the MCP server actually exposes.
# 4. Unit tests for the MCP server and the gateway (tests/).

set -euo pipefail
KIT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$KIT_DIR"

# Keep the run hermetic even if the caller has credentials exported.
unset GEMINI_API_KEY GOOGLE_API_KEY GOOGLE_GENAI_USE_VERTEXAI GOOGLE_CLOUD_PROJECT \
      ANTHROPIC_API_KEY ANTHROPIC_UPSTREAM_KEY GEMINI4_PLUGIN_API_KEY GEMINI4_ENABLE_AGY_CLI 2>/dev/null || true

step() { printf '\n[%s] %s\n' "$1" "$2"; }

step 1/4 "Config files and shell syntax"
python3 - <<'PY'
import json, sys
from pathlib import Path
files = [p for p in Path(".").rglob("*.json") if ".git" not in p.parts]
for p in files:
    json.loads(p.read_text(encoding="utf-8"))
toml_files = [Path("codex/config.toml.example")]
try:
    import tomllib
    for p in toml_files:
        tomllib.loads(p.read_text(encoding="utf-8"))
    note = f", {len(toml_files)} TOML"
except ImportError:  # Python < 3.11
    note = " (TOML check needs Python 3.11+)"
print(f"  ok: {len(files)} JSON{note}")
PY
for f in install.sh verify.sh; do bash -n "$f"; done
echo "  ok: shell syntax"

step 2/4 "Claude Code plugin manifests"
if command -v claude >/dev/null 2>&1; then
  claude plugin validate plugins/gemini >/dev/null
  claude plugin validate . >/dev/null
  echo "  ok: claude plugin validate (plugin and marketplace)"
else
  echo "  skipped: claude CLI not installed"
fi

step 3/4 "Skill and agent tool references"
python3 - <<'PY'
import importlib.util, re, sys
from pathlib import Path
spec = importlib.util.spec_from_file_location("srv", "plugins/gemini/mcp/gemini4_mcp_server.py")
srv = importlib.util.module_from_spec(spec); spec.loader.exec_module(srv)
exposed = {t["name"] for t in srv.TOOLS}
prefix = "mcp__plugin_gemini_gemini4__"
bad, count = [], 0
for md in list(Path("plugins/gemini/skills").glob("*/SKILL.md")) + list(Path("plugins/gemini/agents").glob("*.md")):
    front = md.read_text(encoding="utf-8").split("---")[1]
    for ref in re.findall(r"mcp__[A-Za-z0-9_\-]+", front):
        count += 1
        if not ref.startswith(prefix) or ref[len(prefix):] not in exposed:
            bad.append(f"{md}: {ref}")
    name = re.search(r"^name:\s*(\S+)", front, re.M)
    if md.name == "SKILL.md" and (not name or name.group(1) != md.parent.name):
        bad.append(f"{md}: name does not match directory")
if bad:
    print("\n".join("  FAIL " + b for b in bad)); sys.exit(1)
print(f"  ok: {count} MCP tool references resolve to exposed tools")
PY

step 4/4 "Unit tests"
python3 -m unittest discover -s tests 2>&1 | tail -n 4

printf '\nAll checks passed.\n'
