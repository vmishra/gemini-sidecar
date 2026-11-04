# Changelog

## 2.2.0 (2026-11-04)

### Added
- `estimate_only` on the analyze, security audit, refactor and spec-check tools: files, tokens, estimated cost and typical time, without calling Gemini. The audit, refactor and map commands preview automatically for large scopes.
- Optional large-read guard for Claude Code (`GEMINI_SIDECAR_READ_GUARD=suggest|block`, off by default). It points whole-file reads of large files to `/gemini:analyze`; partial reads always pass.
- README section "When not to use it".

### Changed
- Test logs keep their evidence. Every failure, error, traceback and `file:line` line in a large log is kept along with the tail, and dropped line ranges are marked in place. Previously only the tail was kept.
- When the context budget is reached, answers name the files that were left out instead of only counting them.
- Refactor and test generation include an existing file as a style reference.
- Tool descriptions are shorter, and a test now caps the schema footprint. This matters for hosts that load every tool schema on every turn.

## 2.1.1 (2026-11-04)

### Security
- Redact passwords embedded in URLs (`https://user:password@host`, database connection strings) in everything sent to Gemini.
- `/gemini:deps` never forwards URL-style dependency versions, which can carry credentials. They appear as `<url or path>`.

## 2.1.0 (2026-11-04)

### Added
- `/gemini:deps`: checks dependency manifests against live Google Search results (latest versions, CVEs affecting the declared versions, breaking changes) and lists its sources. Common manifest formats are parsed exactly, so declared versions are never misread.
- `/gemini:spec-check`: checks code against a PDF, Markdown or text spec in the repository, or a URL, requirement by requirement.
- `/gemini:see`: debugs from screenshots or short screen recordings alongside the source code.
- `/gemini:map`: writes an `ARCHITECTURE.md` onboarding guide for the repository, staged for review.
- MCP tools `gemini4_check_dependencies`, `gemini4_spec_check` and `gemini4_visual_debug`, plus an `architecture` mode for `gemini4_long_decode_refactor`.

### Fixed
- README: the prefix-free example now uses `/analyze`. Bare `/review` runs Claude Code's built-in review.

## 2.0.0 (2026-11-03)

First release as `gemini-sidecar` (previously `gemini4-harness-kit`).

### Added
- Claude Code plugin `gemini` with nine commands: `/gemini:analyze`, `security-audit`, `review`, `refactor`, `test-gen`, `test-triage`, `docs`, `ask-antigravity`, `status`.
- MCP tools `gemini4_review_diff` and `gemini4_triage_failures`.
- Subagents `gemini-explorer` and `gemini-implementer`.
- Real token usage and cost reporting, from the API's usage data.
- Offline test suite for the MCP server and the gateway.

### Security
- File reads are confined to the workspace. They follow `.gitignore`, never read secret files or `.git/`, and redact common token formats.
- Generated files are written only to `.gemini4-staging/`. Paths into `.git/` and symlinked staging folders are refused.
- Gateway: a token is required on every endpoint except `/health`, browser requests are rejected (`Origin`/`Host` checks), request size is limited, and the API key is sent in a header.
- The Antigravity CLI runs on redacted copies of the approved files, with a scrubbed environment.
- Six issues found by running the security audit on this repository were fixed.

### Changed
- Codex CLI and Cursor integrate through the MCP server.
- The gateway forwards Anthropic requests unchanged and never reroutes a conversation based on prompt content.

### Removed
- The claude-code-router worker, the Codex profile and agent files, and the OpenAI-compatible gateway endpoints. They did not work as documented.
