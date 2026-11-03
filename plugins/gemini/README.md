# gemini (Claude Code plugin)

Gemini-backed slash commands for Claude Code. A bundled MCP server reads files from disk and sends them to Gemini, so only the answer enters your conversation.

## Install

```text
/plugin marketplace add vmishra/gemini4-harness-kit
/plugin install gemini@gemini4-harness-kit
```

One step on Claude Code 2.1.275 or later:

```text
/plugin install gemini --marketplace vmishra/gemini4-harness-kit
```

Credentials: run `/plugin configure gemini@gemini4-harness-kit` to store a Gemini API key, or set `GEMINI_API_KEY`. For Vertex AI, set `GOOGLE_GENAI_USE_VERTEXAI=true` and `GOOGLE_CLOUD_PROJECT`, and run `gcloud auth application-default login`. Restart Claude Code, then run `/gemini:status`.

## Commands

- `/gemini:analyze <question> [paths] [--deep]`
- `/gemini:security-audit [paths] [--focus area]`
- `/gemini:review [base] [--staged] [--fast]`
- `/gemini:refactor <change> [paths]`
- `/gemini:test-gen <paths>`
- `/gemini:test-triage [command]`
- `/gemini:docs <paths>`
- `/gemini:ask-antigravity [question]`
- `/gemini:status`

## Subagents

- `gemini-explorer`: read-only exploration that sends large file sets to Gemini.
- `gemini-implementer`: implements a well-specified change in an isolated git worktree, using Gemini for bulk generation and local tests for verification.

See the [repository README](../../README.md) for details on what data is sent, configuration, and troubleshooting.
