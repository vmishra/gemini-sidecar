<div align="center">

<img src="./assets/hero-banner.svg" alt="gemini4-harness-kit" width="100%" />

[![Verify](https://github.com/vmishra/gemini4-harness-kit/actions/workflows/verify.yml/badge.svg)](https://github.com/vmishra/gemini4-harness-kit/actions/workflows/verify.yml)
[![Python 3.9+](https://img.shields.io/badge/python-3.9%2B%20stdlib%20only-4285F4)](./verify.sh)
[![License: Apache-2.0](https://img.shields.io/badge/license-Apache--2.0-34A853)](./LICENSE)

</div>

Use Gemini from the coding agent you already have. This kit adds Gemini-backed commands to **Claude Code**, an MCP server for **Codex CLI** and **Cursor**, and an optional local gateway that runs Claude Code subagents (or whole sessions) on Gemini.

The core idea: your agent passes **file paths**, not file contents. A local MCP server reads the files, sends them to Gemini's 1M-token context, and returns a short answer. Large reads, security audits, diff reviews and long code generations no longer fill your agent's context window, and the main conversation stays on the model you picked.

Everything is plain Python 3.9+ standard library. There is nothing to `pip install`.

## Commands (Claude Code)

| Command | What it does | Default model |
|---|---|---|
| `/gemini:analyze <question> [paths] [--deep]` | Answers a question about many files: architecture, call paths, root causes | `gemini-3.8-flash` (`--deep`: `gemini-4-argon`) |
| `/gemini:security-audit [paths] [--focus area]` | Security review with CWE IDs and `path:line` evidence. Defaults to changed files | `gemini-4-argon` |
| `/gemini:review [base] [--staged] [--fast]` | Pre-commit review of the git diff. The server runs `git diff` itself | `gemini-4-argon` |
| `/gemini:refactor <change> [paths]` | Large multi-file refactor, staged in `.gemini4-staging/` for review | `gemini-4-argon` |
| `/gemini:test-gen <paths>` | Generates tests in the project's own style, staged for review | `gemini-4-argon` |
| `/gemini:test-triage [command]` | Runs the tests, writes the log to a file, and root-causes failures | `gemini-3.8-flash` |
| `/gemini:docs <paths>` | Writes or refreshes docstrings and docs, staged for review | `gemini-4-argon` |
| `/gemini:ask-antigravity [question]` | Independent second opinion on the current plan, through the Antigravity CLI when enabled | `gemini-4-argon` |
| `/gemini:status` | Configuration, credentials, and token usage and cost for the session | none |

When no other plugin uses the same name, you can drop the prefix: `/review` instead of `/gemini:review`.

Commands only send code to Google when you run them. Claude can also call the underlying MCP tools on its own when a task fits (a bundled skill tells it when). Claude Code asks for permission the first time unless you allow the tools.

## Quick start

### Claude Code

```text
/plugin marketplace add vmishra/gemini4-harness-kit
/plugin install gemini@gemini4-harness-kit
```

Then provide credentials in one of two ways:

- **Gemini API key** (a paid key from Google AI Studio): run `/plugin configure gemini@gemini4-harness-kit`, or `export GEMINI_API_KEY=...` before starting Claude Code.
- **Vertex AI**:
  ```bash
  gcloud auth application-default login
  export GOOGLE_GENAI_USE_VERTEXAI=true GOOGLE_CLOUD_PROJECT=your-project GOOGLE_CLOUD_LOCATION=global
  ```

Restart Claude Code and run `/gemini:status` to confirm.

### From a clone (Claude Code, Codex CLI, Cursor)

```bash
git clone https://github.com/vmishra/gemini4-harness-kit.git
cd gemini4-harness-kit
./install.sh --doctor      # read-only check; never prints secret values
./install.sh --all         # installs for each harness found on this machine
./verify.sh                # offline tests, no credentials needed
```

`install.sh` backs up every file before changing it (`<file>.bak.<timestamp>`) and supports `--dry-run`.

## How it works

<p align="center">
  <img src="./assets/architecture.svg" alt="Architecture: the agent passes paths to a local MCP server that calls Gemini; an optional gateway runs Claude Code subagents on Gemini" width="100%" />
</p>

**A. MCP server** ([`plugins/gemini/mcp/gemini4_mcp_server.py`](./plugins/gemini/mcp/gemini4_mcp_server.py)). This is a stdio MCP server that works with any MCP-capable harness. It exposes seven tools: `gemini4_analyze_codebase`, `gemini4_security_audit`, `gemini4_review_diff`, `gemini4_long_decode_refactor`, `gemini4_triage_failures`, `ask_antigravity`, and `gemini4_status`.

**B. Gateway** ([`router/gemini4_gateway.py`](./router/gemini4_gateway.py)). This part is optional and only for Claude Code. It is a local implementation of the Anthropic Messages API. Claude Code uses it as `ANTHROPIC_BASE_URL`, and each request is sent to Gemini or forwarded to Anthropic. Two profiles are provided:

| Profile | Main conversation | Subagents | Background (Haiku role) | Needs |
|---|---|---|---|---|
| **Hybrid** (`claude/settings.hybrid-role-pinning.json`) | `claude-opus-5-5`, forwarded to Anthropic unchanged | `gemini-3.8-flash` | `gemini-3.5-flash-lite` | `ANTHROPIC_UPSTREAM_KEY` for the gateway |
| **All-Gemini** (`claude/settings.all-gemini-tiered.json`) | `gemini-4-argon` | `gemini-3.8-flash` | `gemini-3.5-flash-lite` | Gemini credentials only |

The gateway never moves a session's main conversation to a different model partway through. Switching providers mid-thread would discard the prompt cache, and Gemini and Anthropic tool-call histories are not interchangeable.

## What leaves your machine

The MCP server sends file contents to the Gemini API (or to Vertex AI in your project) only when a tool is called. Before anything is sent:

- Paths must resolve inside the workspace (the project directory Claude Code was started in, or `GEMINI4_WORKSPACE_ROOT`). Absolute paths elsewhere, `..` segments and symlinks that point outside are rejected.
- Inside a git repository, directories are expanded with `git ls-files`, so anything in `.gitignore` is skipped.
- Files that commonly hold secrets are never read, even when named explicitly. This covers `.env*`, `*.pem`, `*.key`, SSH keys, `credentials*`, `*.tfstate`, `*.tfvars`, `.npmrc`, `.netrc`, kubeconfigs and similar.
- Common token formats are redacted from everything that is sent: private keys, Google, AWS, GitHub, Slack, Stripe, OpenAI and Anthropic keys, and JWTs. The tool output reports how many were redacted and which files were excluded.
- Generated code is written only under `.gemini4-staging/<run>/` (git-ignored automatically). Paths into `.git/` are refused, and a symlinked staging folder is rejected. Nothing in your working tree changes until you apply it.
- When `ask_antigravity` uses the Antigravity CLI, `agy` runs in a temporary directory that holds redacted copies of only the files that passed these checks. It never sees the real workspace.
- The server refuses to run with your home directory or the filesystem root as its workspace.

Your data handling terms are those of the Gemini API or Vertex AI account you use. For enterprise controls (VPC Service Controls, data residency, CMEK), use Vertex AI.

The gateway listens on `127.0.0.1` only and requires a token on every endpoint except `/health`. It rejects requests that carry a browser `Origin` header or an unexpected `Host` header, which blocks drive-by requests from web pages, including DNS rebinding. It never logs prompt text.

## Codex CLI

```bash
./install.sh --codex
```

This appends a `[mcp_servers.gemini4]` block to `~/.codex/config.toml` (see [`codex/config.toml.example`](./codex/config.toml.example)). Copy [`codex/AGENTS.md`](./codex/AGENTS.md) into a project to tell Codex when to use the tools. Codex keeps using its own model, and the Gemini tools handle the heavy reads.

## Cursor

```bash
./install.sh --cursor
```

This adds the `gemini4` server to `~/.cursor/mcp.json` and installs two read-only subagents in `~/.cursor/agents/`:
- `gemini4-explorer` (`gemini-3.8-flash`)
- `gemini4-security-auditor` (`gemini-4-argon`)

For project rules, copy [`cursor/rules/gemini4-coexistence.mdc`](./cursor/rules/gemini4-coexistence.mdc) into `<project>/.cursor/rules/`. The subagents use Cursor's own Gemini models; check that the model names match those listed in your Cursor plan.

## Using the gateway with Claude Code

```bash
# 1. Start the gateway. The first start creates ~/.config/gemini4/gateway-token (mode 0600).
export GOOGLE_GENAI_USE_VERTEXAI=true GOOGLE_CLOUD_PROJECT=your-project   # or GEMINI_API_KEY=...
export ANTHROPIC_UPSTREAM_KEY=sk-ant-...                                  # Hybrid profile only
python3 router/gemini4_gateway.py

# 2. In another terminal, write a profile into your project and start Claude Code.
./install.sh --gateway-profile all-gemini --project /path/to/project    # or: hybrid
cd /path/to/project && claude
```

The profiles read the gateway token with `apiKeyHelper`, so the token is not stored in the settings file. They also set:
- `CLAUDE_CODE_USE_VERTEX=0` and `CLAUDE_CODE_USE_BEDROCK=0`, because either one, when set globally, makes Claude Code bypass `ANTHROPIC_BASE_URL`.
- `CLAUDE_CODE_SUBAGENT_MODEL_FORCE=1`, so built-in subagents also run on `gemini-3.8-flash`.

Gateway limitations:

- Only the Anthropic Messages API (`/v1/messages`, `/v1/messages/count_tokens`, `/v1/models`) is implemented. OpenAI-style endpoints return HTTP 501; Codex and Cursor should use the MCP server.
- Gemini responses are not streamed token by token. The gateway makes one call and sends SSE `ping` events while waiting.
- `count_tokens` is an estimate (characters divided by 4).
- Spend caps (`GEMINI4_SESSION_BUDGET_USD`, `GEMINI4_GLOBAL_BUDGET_USD`) are estimates held in memory, and they reset when the gateway restarts.

For a shared, centrally managed proxy, [`router/litellm/litellm_config.yaml`](./router/litellm/litellm_config.yaml) is a starting point for LiteLLM. It is not exercised by this repository's CI.

## Cost model

The figures below are an illustrative 40-turn session priced at list prices as of 3 November 2026. They are not a benchmark: your costs depend on how much work your agent delegates.

**Token assumptions:**

| Component | Assumed tokens |
|---|---|
| Main conversation, 40 turns | 0.137M new input, 3.003M cached input, 0.048M output |
| 20 exploration subagents | 0.8M new input, 1.6M cached input, 0.04M output |
| 30 background calls | 0.12M input (not cached), 0.006M output |

New input is billed at the cache-write rate on Claude and at the normal input rate on Gemini.

**Cost per session:**

| Setup | Main | Subagents | Background | Total | vs. baseline |
|---|---:|---:|---:|---:|---:|
| `claude-opus-5-5` for everything | $2.25 | $5.12 | $0.60 | **$7.97** | baseline |
| Hybrid: Opus main, Gemini subagents and background | $2.25 | $0.87 | $0.05 | **$3.17** | −60% |
| All-Gemini, Argon introductory price (through 30 Nov 2026) | $1.05 | $0.87 | $0.05 | **$1.98** | −75% |
| All-Gemini, Argon standard price (from 1 Dec 2026) | $2.11 | $0.87 | $0.05 | **$3.03** | −62% |

**Prices used (USD per 1M tokens: input / cached input / output):**

| Model | Prices | Dates |
|---|---|---|
| `claude-opus-5-5` | $4.00 / $0.20 / $20.00 | Cache write $5.00 |
| `gemini-4-argon` | $2.00 / $0.10 / $10.00 | Introductory, through 30 Nov 2026; then $4.00 / $0.20 / $20.00 |
| `gemini-3.8-flash` | $0.75 / $0.075 / $3.75 | Through 31 Dec 2026; $1.50 / $7.50 input/output from 1 Jan 2027 |
| `gemini-3.5-flash-lite` | $0.30 / $0.03 / $2.50 | |

Gemini applies implicit caching automatically to repeated prompt prefixes of at least 4,096 tokens, with no cache-write fee. Check current prices on the official pricing pages before relying on these numbers. `/gemini:status` reports the tokens and estimated cost of your actual calls, and `GEMINI4_PRICES_JSON` overrides the price table.

## Configuration

| Variable | Purpose |
|---|---|
| `GEMINI_API_KEY` / `GOOGLE_API_KEY` | Gemini API key |
| `GOOGLE_GENAI_USE_VERTEXAI`, `GOOGLE_CLOUD_PROJECT`, `GOOGLE_CLOUD_LOCATION` | Use Vertex AI (location defaults to `global`) |
| `GEMINI4_PRIMARY_MODEL`, `GEMINI4_SUBAGENT_MODEL`, `GEMINI4_BACKGROUND_MODEL` | Override the pro, flash and flash-lite model IDs |
| `GEMINI4_SECURITY_MODEL` | Model for security audits, if different from the pro model |
| `GEMINI4_WORKSPACE_ROOT` | Directory the MCP server may read (default: the project directory) |
| `GEMINI4_MAX_CONTEXT_CHARS`, `GEMINI4_MAX_FILES`, `GEMINI4_MAX_FILE_BYTES` | Per-call limits (defaults: 2.4M chars, 1,500 files, 1 MB per file) |
| `GEMINI4_REQUEST_TIMEOUT` | Seconds per Gemini call (default 900) |
| `GEMINI4_ENABLE_AGY_CLI=1` | Let `ask_antigravity` use the Antigravity CLI (`agy`) in read-only plan mode |
| `GEMINI4_PRICES_JSON` | Price overrides, e.g. `{"gemini-4-argon": [4.0, 0.2, 20.0]}` |
| `GEMINI4_GATEWAY_PORT`, `GEMINI4_GATEWAY_TOKEN` | Gateway port (default 3456) and token (default: generated token file) |
| `ANTHROPIC_UPSTREAM_KEY` | Gateway only: Anthropic key for forwarding Claude models (Hybrid) |
| `GEMINI4_UNMAPPED_MODEL` | Gateway only: Gemini model for non-Gemini model IDs when no Anthropic key is set (default `gemini-3.8-flash`) |
| `GEMINI4_SESSION_BUDGET_USD`, `GEMINI4_GLOBAL_BUDGET_USD` | Gateway only: estimated spend caps |

## Troubleshooting

| Symptom | Cause and fix |
|---|---|
| `/gemini:status` says the backend is not configured | Set credentials (see Quick start) and restart the harness. The MCP server reads its environment at startup. |
| `CERTIFICATE_VERIFY_FAILED` | This happens with python.org builds of Python on macOS that have no CA bundle. The server falls back to `/etc/ssl/cert.pem`. You can also run `Install Certificates.command` from your Python folder. |
| Claude Code ignores the gateway | `CLAUDE_CODE_USE_VERTEX` or `CLAUDE_CODE_USE_BEDROCK` is set globally. The provided profiles override both; check your own settings files. |
| Gateway returns 401 | The token doesn't match. The profiles read `~/.config/gemini4/gateway-token`; if you set `GEMINI4_GATEWAY_TOKEN`, use the same value in Claude Code. |
| `ask_antigravity` notes that it used the Gemini API instead | `agy` is missing or not signed in, or headless mode denied an action. The tool falls back to a direct API call and says why. |
| HTTP 404 for a model | Your project does not have access to that model ID, or the location is wrong. Gated models need explicit access. |
| `/gemini:test-triage` asks for permission | Writing test output to `.gemini4-staging/` is a file write, so Claude Code asks you to approve it once. |

## Development

```bash
./verify.sh                                  # config checks, plugin validation and unit tests; offline
python3 -m unittest discover -s tests -v     # unit tests only
```

```text
.claude-plugin/marketplace.json     Claude Code marketplace
plugins/gemini/                     Claude Code plugin: skills (commands), agents, MCP server
router/gemini4_gateway.py           Optional Anthropic Messages API gateway
router/litellm/                     LiteLLM starting point
claude/                             Gateway profiles for Claude Code
codex/                              Codex CLI MCP config and AGENTS.md
cursor/, .cursor-plugin/            Cursor MCP config, rule and subagents
tests/                              Unit tests (no network)
install.sh, verify.sh               Installer and offline verification
```

## License

[Apache License 2.0](./LICENSE)
