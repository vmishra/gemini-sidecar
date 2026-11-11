# Reference

## The ten MCP tools

| Tool | Does | Default model |
|---|---|---|
| `gemini4_analyze_codebase` | Answers a question over files, directories or globs | `gemini-3.8-flash` (`model_tier: "pro"` for `gemini-4-carbon`) |
| `gemini4_security_audit` | Findings table: severity, CWE, `path:line`, exploit path, fix | `gemini-4-carbon` |
| `gemini4_review_diff` | Reviews `git diff` against a base ref; ends with a verdict | `gemini-4-carbon` |
| `gemini4_long_decode_refactor` | Writes complete files to `.gemini4-staging/` (`mode`: refactor, tests, docs, architecture) | `gemini-4-carbon`, up to 65,536 output tokens |
| `gemini4_triage_failures` | Root-causes failures from a saved log plus source files | `gemini-3.8-flash` |
| `gemini4_check_dependencies` | Checks manifests against live Google Search results: latest versions, CVEs, breaking changes, with sources | `gemini-3.8-flash` + Google Search grounding |
| `gemini4_spec_check` | Checks code against a PDF/Markdown/text spec in the repo or a URL, requirement by requirement | `gemini-4-carbon` (the server fetches URL specs itself: https and public hosts only, on every redirect) |
| `gemini4_visual_debug` | Screenshots or screen recordings plus source code: what is wrong on screen and which lines cause it | `gemini-3.8-flash` |
| `ask_antigravity` | Independent critique; uses `agy` in read-only plan mode when enabled | `gemini-4-carbon` |
| `gemini4_status` | Configuration, token usage and cost for the session | none |


## Configuration

| Variable | Purpose |
|---|---|
| `GEMINI_API_KEY` / `GOOGLE_API_KEY` | Gemini API key. In Claude Code you can store it with `/plugin configure gemini@gemini-sidecar` |
| `GOOGLE_GENAI_USE_VERTEXAI`, `GOOGLE_CLOUD_PROJECT`, `GOOGLE_CLOUD_LOCATION` | Use Vertex AI (location defaults to `global`) |
| `GEMINI4_PRIMARY_MODEL`, `GEMINI4_SUBAGENT_MODEL`, `GEMINI4_BACKGROUND_MODEL` | Override the pro, flash and flash-lite models |
| `GEMINI4_SECURITY_MODEL` | Model for audits, if different from the pro model |
| `GEMINI4_WORKSPACE_ROOT` | Folder the server may read (default: the project directory) |
| `GEMINI4_MAX_CONTEXT_TOKENS`, `GEMINI4_ANALYZE_MAX_TOKENS`, `GEMINI4_MAX_CONTEXT_CHARS`, `GEMINI4_MAX_FILES`, `GEMINI4_MAX_FILE_BYTES` | Per-call limits (750K estimated tokens, 400K for `/gemini:analyze`, 4M chars, 1,500 files, 1 MB per file). When a scope does not fit, source code is read first, directories take turns, and translation catalogs, lockfiles, generated code and SVG come last. |
| `GEMINI4_REQUEST_TIMEOUT` | Seconds per Gemini call (default 900) |
| `GEMINI4_MAX_MEDIA_BYTES` | Total size of images, video and PDFs per call (default 14 MB; inline requests are limited to about 20 MB after encoding) |
| `GEMINI4_ENABLE_AGY_CLI=1` | Let `/gemini:ask-antigravity` use the Antigravity CLI |
| `GEMINI4_INCLUDE_IGNORED=1` | Allow gitignored files that are named explicitly (skipped by default) |
| `GEMINI4_FAILOVER_TO_GEMINI=1` | Gateway, Hybrid: on an Anthropic 429/529, move the session to `gemini-4-carbon` (sends the conversation to Google). Off by default. |
| `GEMINI_SIDECAR_READ_GUARD` | `off` (default), `suggest` or `block`: see [Large-read guard](#large-read-guard) |
| `GEMINI_SIDECAR_READ_GUARD_LINES` | Line threshold for the guard (default 400) |
| `GEMINI4_PRO_THINKING_LEVEL` | Thinking level for the Pro model: `low`, `medium` or `high`. Overrides the per-tool default. |
| `GEMINI4_MAX_CONTINUATIONS` | Long-decode segments to follow before stopping (default 8). |
| `GEMINI4_PRICES_JSON` | Price overrides, e.g. `{"gemini-4-carbon": [4.0, 0.2, 20.0]}` |
| `GEMINI4_GATEWAY_PORT`, `GEMINI4_GATEWAY_TOKEN` | Gateway port (3456) and token (default: generated file) |
| `ANTHROPIC_UPSTREAM_KEY` | Gateway, Hybrid: Anthropic key for forwarded requests |
| `GEMINI4_UNMAPPED_MODEL` | Gateway: Gemini model for other model names when no Anthropic key is set (default `gemini-3.8-flash`) |
| `GEMINI4_SESSION_BUDGET_USD`, `GEMINI4_GLOBAL_BUDGET_USD` | Gateway: estimated spend caps |


## Cost preview

`gemini4_analyze_codebase`, `gemini4_security_audit`, `gemini4_long_decode_refactor` and `gemini4_spec_check` accept `estimate_only: true`. The server collects the files exactly as it would for a real call, then returns the file count, input tokens, typical output tokens, estimated cost and typical time, without calling Gemini. The estimates are fitted to measured runs and landed within about 10% of the actual cost on them. `/gemini:security-audit`, `/gemini:refactor` and `/gemini:map` preview automatically for large scopes.

## Large-read guard

An optional Claude Code hook for whole-file reads of large files:

| `GEMINI_SIDECAR_READ_GUARD` | Behaviour |
|---|---|
| `off` (default) | Nothing happens; the hook exits immediately. |
| `suggest` | The read goes ahead, and Claude gets a note pointing to `gemini4_analyze_codebase`. |
| `block` | The read is refused with that note; Claude reads the section it needs, or asks Gemini. |

Reads with `offset` or `limit` always pass, because edits need exact lines. Images, PDFs, notebooks and staged output also pass, and any error in the hook lets the read proceed. In testing, current Claude models already read large files selectively, so treat the guard as a safety net for long sessions rather than a large saving.

## Troubleshooting

| Symptom | Fix |
|---|---|
| `/gemini:status` says the backend is not configured | Set credentials (see [Try it](../README.md#install)) and restart. The server reads its environment at startup. |
| `CERTIFICATE_VERIFY_FAILED` | python.org builds of Python on macOS ship without CA certificates. The server falls back to `/etc/ssl/cert.pem`; you can also run `Install Certificates.command`. |
| Claude Code ignores the gateway | `CLAUDE_CODE_USE_VERTEX` or `CLAUDE_CODE_USE_BEDROCK` is set globally. The profiles override both; check your own settings files. |
| Gateway returns 401 | The token doesn't match. The profiles read `~/.config/gemini4/gateway-token`. If you set `GEMINI4_GATEWAY_TOKEN`, use the same value for Claude Code. |
| HTTP 404 for a model | Your project or key can't access that model in that location. |
| An audit takes minutes | Expected on `gemini-4-carbon` with high reasoning. Narrow the paths, or use `analyze --deep` for a faster, less exhaustive read. |
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
