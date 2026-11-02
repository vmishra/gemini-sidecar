# Gemini 4 Coexistence Rules for OpenAI Codex CLI (v0.159+ — Nov 2026)

To preserve the main thread's prompt cache while minimizing session cost (`60.2%–75.1%` savings):

1. **Built-in `explorer` Subagent (`claude-gemini-3.8-flash`, 133 tok/s, $0.75/M)**:
   - Delegate broad directory discovery, dependency mapping, and test-log triage to `explorer` (overridden in `.codex/agents/explorer.toml`).
2. **1M Synthesis & Security Gate (`argon-reviewer` / `gemini4_security_audit`)**:
   - Delegate whole-repo architectural synthesis (`>150K` tokens) and CWE/CVE vulnerability audits to `argon-reviewer` (`claude-gemini-4-argon`, `high` effort, 2-hour `stream_idle_timeout_ms = 7200000`) or call MCP `gemini4_security_audit(paths=[...])`.
3. **Cross-Family Second Opinion (`ask_antigravity`)**:
   - Before executing risky multi-module refactors, invoke `ask_antigravity` (`agy -p --add-dir`) for an independent Google Antigravity plan review.
4. **Never Dump Massive Files Into Tool Arguments**:
   - Pass workspace-relative `paths` to `gemini4_analyze_codebase`, `gemini4_security_audit`, and `gemini4_long_decode_refactor` so raw source files hit Gemini's 95%-discounted implicit cache (`$0.075/M` Flash, `$0.10/M` Argon) without bloating the parent Codex context window.
