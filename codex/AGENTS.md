# Using the Gemini tools from Codex

The `gemini4` MCP server reads files from disk and sends them to Gemini, returning only the answer. Use it when reading the material yourself would fill your context:

- `gemini4_analyze_codebase`: questions spanning many files (architecture, call paths, root causes). Use `model_tier: "pro"` for cross-module reasoning.
- `gemini4_security_audit`: security review of a directory or change set.
- `gemini4_review_diff`: review uncommitted changes, or a branch against a base ref, before committing.
- `gemini4_long_decode_refactor`: large generated changes (refactors, test suites, docs). Output goes to `.gemini4-staging/<run>/`. Review it before copying anything into the working tree.
- `gemini4_triage_failures`: write test output to `.gemini4-staging/test-output.log`, then pass that path.
- `ask_antigravity`: independent critique of a plan before a risky change.
- `gemini4_status`: configuration and token usage for the session.

Always pass workspace-relative paths, never file contents. Verify cited `path:line` locations before you edit code.
