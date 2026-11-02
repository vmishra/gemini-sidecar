# `gemini4-coexistence` Claude Code Plugin (v1.2.0)

Cache-preserving Gemini 4 Argon (`gemini-4-argon` GA), Gemini 3.8 Flash (`133 tok/s`), Gemini 3.5 Flash-Lite (`454 tok/s`), Fairwind Gemini 4 Carbon readiness, and Google Antigravity (`ask_antigravity`) plugin for Claude Code `v2.1.302+` (with `claude mcp add` fallback for `v1.x`).

## 1-Step Installation

Inside Claude Code `v2.1.275+`:

```text
/plugin install gemini4-coexistence --marketplace vmishra/gemini4-harness-kit
```

Or from a local clone of `gemini4-harness-kit/`:

```bash
./install.sh --claude
```

## Exposed Components

- **6 File-Pointer MCP Tools (`gemini4_mcp_server.py`)**:
  - `ask_antigravity`: Cross-family `CLAUDE_ANTIGRAVITY_LOOP` plan critique & pre-commit review (`agy -p --add-dir`).
  - `gemini4_analyze_codebase`: Reads `paths` directly from disk into Gemini's 1.05M window (`flash`, `argon`, or `flash-lite`) without bloating Claude's chat transcript.
  - `gemini4_security_audit`: CWE/CVE taint-flow audit on GA `gemini-4-argon` (#1 tied Endor Labs Cursor Agent Security League; auto-upgrades when `GEMINI4_FAIRWIND_CARBON_MODEL` is set).
  - `gemini4_long_decode_refactor`: Stages 32K/64K multi-file refactors into `.gemini4-staging/`.
  - `gemini4_antigravity_task`: Autonomous multi-step verify-and-fix delegation.
  - `gemini4_cache_telemetry`: Live implicit cache warmth & Opus 5.5 cache-write savings report.
- **3 Skills**: `gemini4-coexistence`, `bulk-test-triage` (`context: fork`, `background: false`), `gemini4-security-audit` (`context: fork`, `background: false`).
- **3 Subagents**: `gemini-codebase-explorer`, `argon-security-auditor` (`background: true`), `gemini-worktree-builder` (`isolation: worktree`).
