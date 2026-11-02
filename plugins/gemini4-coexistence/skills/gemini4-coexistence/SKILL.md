---
name: gemini4-coexistence
description: Automatically steer codebase exploration, bulk test triage, 1M-context repo synthesis, security audits, and Antigravity second-opinion reviews to Gemini 3.5 Flash-Lite, Gemini 3.8 Flash, and Gemini 4 Argon while preserving the host session's prompt cache.
---

# Gemini 4 Coexistence & Cache-Safe Dynamic Offloading (v1.1 — Nov 2026)

Use this skill whenever a task benefits from **454 tok/s background classification**, **133 tok/s high-speed subagent exploration**, **1,048,576-token whole-repository synthesis**, **CVE-grade security auditing**, or **cross-family Antigravity verification**—without invalidating the host session's Anthropic/OpenAI prefix cache or risking mid-thread `tool_use.id` / `thought_signature` 400 crashes.

## Golden Rule #1: Never Mutate the Root Thread Provider Mid-Session

Switching models mid-thread on the root conversation forces a full prefix cache miss ($5.00/M Opus 5.5 cache write penalty), strips Gemini's mandatory `thought_signature` tokens, and triggers `400 Bad Request` when 728-char LiteLLM/Gemini tool IDs hit Anthropic's `^[a-zA-Z0-9_-]+$` regex validator.

Instead, **keep the root planner pinned** and offload heavy token volume through **isolated context boundaries**:

1. **File-Pointer MCP Tools (`gemini4_analyze_codebase`, `gemini4_security_audit`, `gemini4_long_decode_refactor`, `ask_antigravity`)**
   - Pass **workspace-relative file/directory paths** (`paths`), NEVER raw file contents in tool arguments.
   - The MCP server reads the files directly from disk into Gemini's 1.05M token window (`$0.075/M` Flash or `$0.10/M` Argon implicit cached reads at >=4,096 tokens, `$0` write fee) and returns a compact markdown synthesis (<1,500 tokens) back to your root context.
2. **Forked Skills (`/gemini4-coexistence:bulk-test-triage`, `/gemini4-coexistence:gemini4-security-audit`)**
   - Uses `context: fork` + `background: false` + `!` shell injection to run isolated worker loops without bloating the main conversation.
3. **Model-Pinned Subagents (`gemini-codebase-explorer`, `argon-security-auditor`, `gemini-worktree-builder`)**
   - Subagents account for **64.2% of session spend** in monolithic Opus 5.5 workflows (`$5.12` of `$7.97`/session). Delegating subagents to `gemini-3.8-flash` cuts total session spend by **60.2% (`$3.17`/session)**, or **75.1% (`$1.98`/session)** on an All-Gemini stack.

## Golden Rule #2: Nov 2026 Automatic Tier Selection Matrix

| Task Archetype | Target Model | Economics & Speed | Why This Tier |
|---|---|---|---|
| **Background Loops, File Indexing, `--permission-mode auto` Safeguard Classifier** | `gemini-3.5-flash-lite` | **$0.30 / $2.50** per M · **454 tok/s** | Fastest model in the Gemini lineup; ideal for `ANTHROPIC_DEFAULT_HAIKU_MODEL` & CCR `background` route. |
| **Repo Exploration, Dependency Mapping, Log/Test Triage, Routine Subagents** | `gemini-3.8-flash` | **$0.75 / $3.75** per M (`$0.075` cached) · **133 tok/s** | **89.4% Terminal-Bench 2.1**, **73.7% DeepSWE v1.1**, **63.5% Toloka pass^5**; exempt from Cursor's `$0.25/M` Token Rate surcharge. |
| **1M-Token Repo Synthesis, Cross-Module Architecture, Deep Refactoring** | `gemini-4-argon` (`thinking_level="high"`) | **$2.00 / $10.00** intro (`$0.10` cached, 95% discount) | 79.3 LiveBench (89.7 Coding, 95.1 Reasoning), 52.8% CursorBench (ties Opus 5.5). Enforces Oct 27 rules (`max_output_tokens >= 32768`, 20m timeout). |
| **Vulnerability Discovery, Exploit Validation, Auth/Crypto/SQLi/SSRF Review** | `gemini-4-argon` (GA today; 1-line Fairwind `Gemini 4 Carbon` hook) | **$2.00 / $10.00** intro (`$0.10` cached) | Tied **#1 on Endor Labs' 200-task Cursor Agent Security League** (29.0% SecPass; uniquely solved CVE-2021-29488 & CVE-2015-8749). Auto-upgrades when `GEMINI4_FAIRWIND_CARBON_MODEL` is set (#1 AA Intelligence v5.0 = **59**, 88.2% SEC-bench Pro). |
| **Cross-Family Plan Critique (`CLAUDE_ANTIGRAVITY_LOOP`)** | `ask_antigravity` (`agy -p --add-dir`) | Flat-rate AI Pro/Ultra or Vertex IAM | Spawns headless Google Antigravity CLI directly on workspace disk for an independent architectural critique before multi-file edits. |

## Recommended Workflow (`CLAUDE_ANTIGRAVITY_LOOP` + File-Pointer Offload)

1. **Scout (`gemini-3.8-flash`)**: Call `gemini4_analyze_codebase(paths=[...], question="...", model_tier="flash")` or spawn `gemini-codebase-explorer` to map unfamiliar directories without loading raw files into the root window.
2. **Critique Plan (`ask_antigravity` or `argon`)**: Before executing complex multi-file migrations, call `ask_antigravity(prompt="Critique this implementation plan...", paths=[...])` or `gemini4_analyze_codebase(..., model_tier="argon")`.
3. **Stage Long Decode (`gemini4_long_decode_refactor`)**: Offload large boilerplate/migrations to `.gemini4-staging/` (`stage_output_to="patch.out"`), inspect, and apply cleanly.
4. **Security Gate (`gemini4_security_audit`)**: Run `gemini4_security_audit(paths=[...])` on modified auth, API, infrastructure, or dependency files before committing.
5. **Telemetry (`gemini4_cache_telemetry`)**: Inspect live cache hits, Oct 27 Argon API compliance, and session USD savings vs monolithic `claude-opus-5-5`.
