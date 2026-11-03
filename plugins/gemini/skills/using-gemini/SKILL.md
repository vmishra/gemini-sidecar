---
name: using-gemini
description: When to hand work to the gemini4 MCP tools instead of reading files directly - large multi-file questions, security review, pre-commit review, long generated output, test-log triage, or a second opinion.
user-invocable: false
---

# When to use the Gemini tools

The gemini4 MCP tools read files from disk on the server side and return only a short answer. Use them when reading the material yourself would put a lot of text into this conversation:

| Situation | Tool |
|---|---|
| A question that needs more than roughly 10 files or 100 KB of source | `gemini4_analyze_codebase` (`model_tier: "pro"` for cross-module reasoning) |
| Security review of a module or change set | `gemini4_security_audit` |
| Reviewing a large diff before commit | `gemini4_review_diff` |
| Generating many files or very long output (migrations, test suites) | `gemini4_long_decode_refactor` (writes to `.gemini4-staging/`) |
| A long test or build log | Redirect output to `.gemini4-staging/test-output.log`, then `gemini4_triage_failures` |
| An independent critique of a plan before a risky change | `ask_antigravity` |

Rules:
- Pass workspace-relative paths, never file contents.
- For one or two small files, read them directly; a Gemini call is not worth the latency.
- Treat Gemini's answer as a strong second opinion, not ground truth. Verify cited lines before editing code.
- Staged output is not applied automatically. Show it to the user and apply it only with their agreement.
