# Gemini 4 Multi-Harness Coexistence Kit

In-harness coexistence configurations, a zero-dependency file-pointer MCP server, and a local protocol-normalizing gateway for running **Gemini 4 Argon** (`gemini-4-argon`), **Gemini 3.8 Flash** (`gemini-3.8-flash`), **Gemini 3.5 Flash-Lite** (`gemini-3.5-flash-lite`), and **Google Antigravity** (`agy`) inside **Claude Code**, **OpenAI Codex CLI**, and **Cursor IDE**.

Designed for engineering teams that want to retain their existing coding harness and root planning workflow while offloading subagent exploration, bulk file ingestion, and background classification onto Gemini—reducing session spend by **60.2% to 75.1%** without breaking prompt caches or triggering cross-provider tool-ID failures.

---

## Problem & Architecture

In a typical 40-turn coding session on a monolithic frontier model (`claude-opus-5-5` at `$7.97/session`), **subagent repository exploration and test triage account for 64.2% of total token spend (`$5.12`)**.

Attempting to save money by manually switching `/model` mid-session introduces two failure modes:
1. **Prompt-Cache Invalidation**: Switching the active root thread invalidates the prefix cache (`$5.00/1M` cache-write penalty on Opus 5.5) and forces full context re-prefill.
2. **Wire-Protocol Collisions**: Gemini and LiteLLM emit extended `tool_use.id` tokens and require `thoughtSignature` replay across function-calling turns; switching a live tool thread back to Anthropic fails `^[a-zA-Z0-9_-]+$` validation with `HTTP 400`.

`gemini4-harness-kit` avoids mid-thread switching entirely. It keeps the **root planning thread pinned to a single model family** so its prefix cache remains warm, and delegates high-volume token work across three isolated execution boundaries:

```text
┌──────────────────────────────────────────────────────────────────────────────┐
│  DEVELOPER HARNESS (Claude Code  ·  OpenAI Codex CLI  ·  Cursor IDE)         │
│  Root Planner Thread stays session-pinned -> warm prefix cache preserved     │
└───────────┬──────────────────────────────┬───────────────────────────┬───────┘
            │                              │                           │
            ▼                              ▼                           ▼
┌───────────────────────────┐  ┌──────────────────────────┐  ┌─────────────────┐
│ 1. SUBAGENT WORKHORSE     │  │ 2. FILE-POINTER MCP      │  │ 3. BACKGROUND   │
│ gemini-3.8-flash          │  │ gemini-4-argon (1M GA)   │  │ 3.5-flash-lite  │
│ 133 tok/s · $0.75/1M      │  │ $2/$10 ($0.10/1M cached) │  │ 454 tok/s       │
│ 89.4% Terminal-Bench 2.1  │  │ Reads paths from disk;   │  │ $0.30/1M        │
│ -83% subagent token cost  │  │ returns <500w synthesis  │  │ Haiku & Auto    │
└───────────────────────────┘  └──────────────────────────┘  └─────────────────┘
```

### Benchmark Session Cost (40 Root Turns + 20 Subagents + 30 Background Calls)

| Architecture | Root Thread | 20 Subagents | 30 Background | Total / Session | Delta vs Baseline |
|---|---:|---:|---:|---:|---|
| Monolithic `claude-opus-5-5` | `$2.25` | `$5.12` | `$0.60` | `$7.97` | Baseline |
| Naive mid-thread `/model` toggling | `$3.84` | `$2.35` | `$0.30` | `$6.49` | `-18.5%` (cache thrash + `400` risk) |
| **Hybrid: `claude-opus-5-5` Root + Gemini Subagents** | `$2.25` | `$0.87` | `$0.05` | **`$3.17`** | **`-60.2%`** (zero root-planner change) |
| **All-Gemini Tiered (`gemini-4-argon` intro thru Nov 30)** | `$1.05` | `$0.87` | `$0.05` | **`$1.98`** | **`-75.1%`** (`$0.10/1M` implicit cache) |
| **All-Gemini Tiered (standard rate Dec 1+)** | `$2.11` | `$0.87` | `$0.05` | **`$3.03`** | **`-62.0%`** (`$0.00` cache-write fee) |

---

## Quickstart

### 1. Clone & Run Pre-Flight Readiness Check

Requires **Python 3.9+** (standard library only; zero `pip` packages). Run the read-only environment doctor to inspect Python, loopback networking, installed CLIs, and credential environment variables (names only; secret values are never printed):

```bash
git clone https://github.com/vmishra/gemini4-harness-kit.git
cd gemini4-harness-kit

./install.sh --doctor
# Machine-readable output for CI or scripts:
./install.sh --doctor --json
```

### 2. Configure Google Credentials

Choose **one** authentication backend before making live Gemini calls:

- **Google AI Studio (Paid Tier 1+)**: Free-tier frontier quota was retired in December 2025; ensure Paid Tier 1+ billing is enabled on the AI Studio project.
  ```bash
  export GEMINI_API_KEY="AIzaSy..."
  ```
- **Google Cloud Vertex AI (IAM / ADC / VPC-SC / ZDR)**:
  ```bash
  gcloud auth application-default login
  export GOOGLE_GENAI_USE_VERTEXAI="true"
  export GOOGLE_CLOUD_PROJECT="your-gcp-project-id"
  export GOOGLE_CLOUD_LOCATION="global"
  ```

---

### Track A: Zero-Proxy Plugin & File-Pointer MCP (60 Seconds)

Use Track A when developers authenticate via **Claude Max / OAuth subscriptions** or native **Cursor** accounts and want to keep their primary harness transport untouched while adding Gemini 4 Argon / 3.8 Flash subagents and disk-offload MCP tools.

```bash
./install.sh --claude --cursor
./verify.sh
```

> **Direct Claude Code Marketplace Install (`v2.1.275+`)**: You can also install the Claude Code plugin directly from GitHub inside `claude`:
> ```text
> /plugin install gemini4-coexistence --marketplace vmishra/gemini4-harness-kit
> ```

- **Claude Code**: Launch `claude`, verify `/mcp` lists `gemini4` (`ask_antigravity`, `gemini4_analyze_codebase`, `gemini4_security_audit`, `gemini4_long_decode_refactor`), or invoke `/gemini4-coexistence:bulk-test-triage` and `/gemini4-coexistence:gemini4-security-audit src/`.
- **Cursor IDE**: Open Composer (`Cmd+I`). Set **Plan** mode (`Shift+Tab`) to an explicit model (`gemini-4-argon` or `claude-opus-5-5`—do not leave parent Composer on `Auto` when invoking custom subagents, per Cursor Issue `#176256`), then invoke `/gemini4-explorer` (`gemini-3.8-flash`, exempt from Cursor's `$0.25/1M` Token Rate surcharge) or `/gemini4-security-auditor`.

---

### Track B: Local Smart Gateway + Automatic Role Pinning (2 Minutes)

Use Track B for automatic wire-level subagent routing (`-60.2%` to `-75.1%` session cost) in Claude Code, **OpenAI Codex CLI (`v0.134`–`v0.159+`)** `/v1/responses` translation, or Cursor Enterprise custom gateways.

```bash
# 1. Install across Claude Code, Codex CLI, Cursor IDE, and CCR/LiteLLM
./install.sh --all
./verify.sh

# 2. Start the zero-dependency gateway on 127.0.0.1:3456
#    (Optional cap: export GEMINI4_SESSION_BUDGET_USD="5.00")
python3 ./router/gemini4_gateway.py &
```

#### Launch Harnesses Against `:3456`

- **Claude Code (`v2.1.302+`)**:
  ```bash
  mkdir -p .claude
  # Hybrid: Opus 5.5 Root + Gemini 3.8 Flash Subagents + 3.5 Flash-Lite Haiku ($3.17/session)
  # (Export ANTHROPIC_UPSTREAM_KEY="sk-ant-..." in the gateway shell for live Opus root turns)
  cp ./claude/settings.hybrid-role-pinning.json .claude/settings.local.json

  # Or All-Gemini Tiered: Argon 1M Root + 3.8 Flash Subagents + 3.5 Flash-Lite ($1.98/session)
  cp ./claude/settings.all-gemini-tiered.json .claude/settings.local.json

  claude
  ```
- **OpenAI Codex CLI (`v0.134+` / `v0.159+`)**:
  ```bash
  # Uses ~/.codex/gemini4.config.toml (Responses API + 2h Argon SSE idle timeout + explorer.toml override)
  codex --profile gemini4

  # High-throughput 3.8 Flash (133 tok/s) on the primary thread
  codex --profile gemini4 --model claude-gemini-3.8-flash

  # Read-only CWE/CVE security audit profile
  codex exec --profile gemini4-security "Audit src/ for auth bypass and SQL injection"
  ```

---

## Security & Credential Hygiene

- **Keep raw API keys out of subprocess environments**: When deploying Claude Code on shared developer workstations, prefer delivering gateway tokens via a `0600`-permissioned helper script (`"apiKeyHelper"` in `settings.local.json`) rather than long-lived shell `env` exports visible to child tools. Do **not** set `CLAUDE_CODE_PROVIDER_MANAGED_BY_HOST=1` alongside `apiKeyHelper` (Claude Code `v2.1.283+` ignores `apiKeyHelper` when that flag is present).
- **Zero raw prompt logging**: `gemini4_gateway.py` records only a 16-hex SHA-256 `prompt_digest` in `/health` and routing traces—never prompt bodies.
- **Risk-word routing floor**: In `claude-auto-gemini` mode, prompts matching security or operational risk stems (`production`, `security`, `auth`, `crypto`, `migration`, `payment`, `delete`, `cve`, `cwe`) are barred from downgrading to `gemini-3.5-flash-lite` regardless of prompt length.
- **Optional per-session spend cap**: Export `GEMINI4_SESSION_BUDGET_USD="5.00"` on the gateway to reject runaway agent loops cleanly with an Anthropic/OpenAI-compatible `HTTP 403` error envelope.

---

## Verification & Qualification Matrix

Run `./verify.sh` to execute all **7 hermetic verification suites** offline (compatible with stock macOS `/usr/bin/python3` `3.9.6` through Python `3.13+`):

| Suite | Scope Verified | Mode |
|---|---|---|
| `[1/7]` | Claude Code plugin & marketplace schemas (`claude plugin validate`), `ANTHROPIC_API_KEY=""` precedence, `ENABLE_TOOL_SEARCH="false"` | Hermetic |
| `[2/7]` | Codex `v0.159+` `wire_api = "responses"`, `stream_idle_timeout_ms = 7200000`, `explorer.toml` override, Argon subagent TOMLs | Hermetic |
| `[3/7]` | Cursor `.cursor-plugin/plugin.json`, subagent frontmatter, Oct 2026 `$0.25/1M` exemption & Issue `#176256` rule | Hermetic |
| `[4/7]` | `claude-code-router` (CCR) Node.js worker (`3.5-flash-lite`, `3.8-flash`, `4-argon` routing) | Hermetic |
| `[5/7]` | Stdio MCP JSON-RPC 2.0 handshake, all 6 tools (`ask_antigravity`, `gemini4_*`), `[1m]` normalization, warm implicit-cache tracking | Hermetic |
| `[6/7]` | Gateway `/model` substring discovery (`claude-gemini-*`), `--permission-mode auto` `safeguard_results`, root session pinning, HTTP `429` sticky failover | Hermetic |
| `[7/7]` | Claude `v2.1.301+` embedded `role: "system"` extraction, `/anthropic/v1/messages/count_tokens`, `/openai/v1/responses` field stripping, `RISK_WORDS` floor, `GEMINI4_SESSION_BUDGET_USD` `403` cap, `--doctor --json` | Hermetic |

---

## Known Harness Nuances & Troubleshooting (Late 2026)

| Symptom / Version Nuance | Root Cause | Built-In Mitigation |
|---|---|---|
| **Claude Code `/model` menu omits Gemini models** | Claude Code `v2.1.302+` filters out gateway model IDs that do not contain `claude` or `anthropic`. | Gateway and LiteLLM expose `claude-gemini-4-argon`, `claude-gemini-3.8-flash`, `claude-gemini-3.5-flash-lite`, and `claude-auto-gemini`. |
| **Claude Code behind `ANTHROPIC_BASE_URL` searches for `Bash`/`Write` instead of calling them** | Deferred tool search assumes Anthropic-native tool-search blocks when `ENABLE_TOOL_SEARCH` is active on non-Anthropic primary models. | `claude/settings.all-gemini-tiered.json` sets `"ENABLE_TOOL_SEARCH": "false"`. |
| **Claude Code `v2.1.301+` sends `role: "system"` inside `messages[]`** | Recent Claude Code builds inject hook/context messages with `role: "system"` inside the `messages` array in addition to top-level `system`. | `gemini4_gateway.py` extracts embedded `role: "system"` items and merges them into Gemini `systemInstruction`. |
| **Claude Code logs `404`/`502` twice per turn on custom gateways** | Claude Code preflights `POST /v1/messages/count_tokens` twice per turn. | `gemini4_gateway.py` serves `POST /v1/messages/count_tokens` (and `/anthropic/v1/messages/count_tokens`) across `system`, `tools`, and `messages`. |
| **Codex CLI fails directly against `googleapis.com/v1beta/openai`** | Codex `v0.159+` removed `/chat/completions` and requires `POST /v1/responses`; Gemini's OpenAI endpoint also rejects `store` and `prompt_cache_key`. | `codex/gemini4.config.toml` routes through `127.0.0.1:3456/v1` (`wire_api = "responses"`) and strips unsupported OpenAI fields. |
| **Headless `agy -p` (`v1.4.7+`) exits `0` without writing files** | `agy` requires `GEMINI_API_KEY` + `"modelProvider": "gemini"` in `~/.gemini/antigravity-cli/settings.json` and soft-denies `WriteFile`/`RunCommand` in `-p` mode (`denied_actions`) without explicit `permissions.allow`. | Read-only `ask_antigravity` critiques run unaffected; `gemini4_mcp_server.py` and `./install.sh --doctor` detect `denied_actions` / missing `modelProvider` and print the exact `permissions.allow` rule. |
| **`HTTP 404` when requesting `gemini-4-carbon`** | Announced Oct 28, 2026 (`#1` AA Intelligence v5.0 = `59`), **Gemini 4 Carbon** is currently gated to Google Cloud's **Fairwind** program. | Defaults to GA `gemini-4-argon` (tied `#1` on Endor Labs' 200-task Cursor Agent Security League); set `GEMINI4_FAIRWIND_CARBON_MODEL` only when enrolled in Fairwind. |

---

## Repository Layout

```text
gemini4-harness-kit/
├── LICENSE                            # Apache License 2.0
├── README.md                          # Architecture, quickstart & troubleshooting guide
├── install.sh                         # Idempotent installer + read-only `--doctor [--json]` + `--dry-run`
├── verify.sh                          # 7-suite hermetic verification runner (Python 3.9–3.13+)
├── .claude-plugin/marketplace.json    # Claude Code v2.1+ Marketplace manifest
├── .cursor-plugin/plugin.json         # Cursor IDE plugin manifest
├── claude/
│   ├── settings.hybrid-role-pinning.json   # Opus 5.5 Root + Gemini 3.8 Flash Subagents (-60.2%)
│   └── settings.all-gemini-tiered.json     # All-Gemini Tiered Stack (-75.1%, ENABLE_TOOL_SEARCH=false)
├── plugins/gemini4-coexistence/
│   ├── .claude-plugin/plugin.json     # Plugin v1.1.0 manifest & interactive userConfig
│   ├── .mcp.json                      # Stdio MCP configuration
│   ├── mcp/gemini4_mcp_server.py      # Zero-dependency File-Pointer MCP + `ask_antigravity` bridge
│   ├── skills/                        # `gemini4-coexistence`, `bulk-test-triage`, `gemini4-security-audit`
│   └── agents/                        # `gemini-codebase-explorer`, `argon-security-auditor`, `gemini-worktree-builder`
├── router/
│   ├── gemini4_gateway.py             # Local HTTP gateway (:3456) for Claude Code, Codex & Cursor
│   ├── litellm/litellm_config.yaml    # Enterprise LiteLLM v1.109.0+ configuration
│   └── ccr/                           # `musistudio/claude-code-router` worker & profiles
├── codex/
│   ├── AGENTS.md                      # Repo-scoped Codex delegation instructions
│   ├── gemini4.config.toml            # Codex Responses API profile (`codex --profile gemini4`)
│   ├── gemini4-security.config.toml   # Read-only CWE/CVE audit profile
│   └── agents/                        # `explorer.toml` override, `argon-reviewer.toml`, `argon-migrator.toml`
└── cursor/
    ├── mcp.json                       # Cursor MCP template
    ├── rules/gemini4-coexistence.mdc  # Post-Oct 2026 surcharge exemption & Issue #176256 rules
    └── agents/                        # `gemini4-explorer.md`, `gemini4-security-auditor.md`, `gemini4-migrator.md`
```
