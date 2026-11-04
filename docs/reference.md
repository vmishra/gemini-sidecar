# Reference

## The ten MCP tools

| Tool | Does | Default model |
|---|---|---|
| `gemini4_analyze_codebase` | Answers a question over files, directories or globs | `gemini-3.8-flash` (`model_tier: "pro"` for `gemini-4-argon`) |
| `gemini4_security_audit` | Findings table: severity, CWE, `path:line`, exploit path, fix | `gemini-4-argon` |
| `gemini4_review_diff` | Reviews `git diff` against a base ref; ends with a verdict | `gemini-4-argon` |
| `gemini4_long_decode_refactor` | Writes complete files to `.gemini4-staging/` (`mode`: refactor, tests, docs, architecture) | `gemini-4-argon`, up to 65,536 output tokens |
| `gemini4_triage_failures` | Root-causes failures from a saved log plus source files | `gemini-3.8-flash` |
| `gemini4_check_dependencies` | Checks manifests against live Google Search results: latest versions, CVEs, breaking changes, with sources | `gemini-3.8-flash` + Google Search grounding |
| `gemini4_spec_check` | Checks code against a PDF/Markdown/text spec in the repo or a URL, requirement by requirement | `gemini-4-argon` (URL context tool for URLs) |
| `gemini4_visual_debug` | Screenshots or screen recordings plus source code: what is wrong on screen and which lines cause it | `gemini-3.8-flash` |
| `ask_antigravity` | Independent critique; uses `agy` in read-only plan mode when enabled | `gemini-4-argon` |
| `gemini4_status` | Configuration, token usage and cost for the session | none |


## Configuration

| Variable | Purpose |
|---|---|
| `GEMINI_API_KEY` / `GOOGLE_API_KEY` | Gemini API key. In Claude Code you can store it with `/plugin configure gemini@gemini-sidecar` |
| `GOOGLE_GENAI_USE_VERTEXAI`, `GOOGLE_CLOUD_PROJECT`, `GOOGLE_CLOUD_LOCATION` | Use Vertex AI (location defaults to `global`) |
| `GEMINI4_PRIMARY_MODEL`, `GEMINI4_SUBAGENT_MODEL`, `GEMINI4_BACKGROUND_MODEL` | Override the pro, flash and flash-lite models |
| `GEMINI4_SECURITY_MODEL` | Model for audits, if different from the pro model |
| `GEMINI4_WORKSPACE_ROOT` | Folder the server may read (default: the project directory) |
| `GEMINI4_MAX_CONTEXT_CHARS`, `GEMINI4_MAX_FILES`, `GEMINI4_MAX_FILE_BYTES` | Per-call limits (2.4M chars, 1,500 files, 1 MB per file) |
| `GEMINI4_REQUEST_TIMEOUT` | Seconds per Gemini call (default 900) |
| `GEMINI4_MAX_MEDIA_BYTES` | Total size of images, video and PDFs per call (default 14 MB; inline requests are limited to about 20 MB after encoding) |
| `GEMINI4_ENABLE_AGY_CLI=1` | Let `/gemini:ask-antigravity` use the Antigravity CLI |
| `GEMINI4_PRICES_JSON` | Price overrides, e.g. `{"gemini-4-argon": [4.0, 0.2, 20.0]}` |
| `GEMINI4_GATEWAY_PORT`, `GEMINI4_GATEWAY_TOKEN` | Gateway port (3456) and token (default: generated file) |
| `ANTHROPIC_UPSTREAM_KEY` | Gateway, Hybrid: Anthropic key for forwarded requests |
| `GEMINI4_UNMAPPED_MODEL` | Gateway: Gemini model for other model names when no Anthropic key is set (default `gemini-3.8-flash`) |
| `GEMINI4_SESSION_BUDGET_USD`, `GEMINI4_GLOBAL_BUDGET_USD` | Gateway: estimated spend caps |


## Troubleshooting

| Symptom | Fix |
|---|---|
| `/gemini:status` says the backend is not configured | Set credentials (see [Try it](../README.md#try-it-in-two-minutes)) and restart. The server reads its environment at startup. |
| `CERTIFICATE_VERIFY_FAILED` | python.org builds of Python on macOS ship without CA certificates. The server falls back to `/etc/ssl/cert.pem`; you can also run `Install Certificates.command`. |
| Claude Code ignores the gateway | `CLAUDE_CODE_USE_VERTEX` or `CLAUDE_CODE_USE_BEDROCK` is set globally. The profiles override both; check your own settings files. |
| Gateway returns 401 | The token doesn't match. The profiles read `~/.config/gemini4/gateway-token`. If you set `GEMINI4_GATEWAY_TOKEN`, use the same value for Claude Code. |
| HTTP 404 for a model | Your project or key can't access that model in that location. |
| An audit takes minutes | Expected on `gemini-4-argon` with high reasoning. Narrow the paths, or use `analyze --deep` for a faster, less exhaustive read. |
| `/gemini:test-triage` asks for permission | Running your tests and saving the log is a command and a file write, so Claude Code asks once. |
| `ask-antigravity` says it used the Gemini API instead | `agy` is missing, signed out, or denied an action in headless mode. The command falls back to a direct call and says why. |


## Development

```bash
./verify.sh                                  # offline: config checks, plugin validation, unit tests
python3 -m unittest discover -s tests -v     # unit tests only (no network, no credentials)
```

```text
plugins/gemini/          Claude Code plugin: commands (skills/), subagents (agents/), MCP server (mcp/)
router/                  Optional gateway; LiteLLM starting point (not covered by CI)
claude/                  Gateway profiles for Claude Code
codex/, cursor/          Codex and Cursor configuration
tests/                   Unit tests
install.sh, verify.sh    Installer and offline checks
```
