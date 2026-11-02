---
name: gemini4-security-audit
description: Deep CWE/OWASP vulnerability, taint-flow, and exploitability audit executed in an isolated forked context via Gemini 4 Argon (with Fairwind Gemini 4 Carbon drop-in support).
context: fork
agent: argon-security-auditor
background: false
allowed-tools: Read, Grep, Glob, mcp__plugin_gemini4-coexistence_gemini4__gemini4_security_audit, mcp__plugin_gemini4-coexistence_gemini4__gemini4_cache_telemetry
disallowed-tools: Write Edit
---

# Isolated Security Audit (`/gemini4-coexistence:gemini4-security-audit`)

## Modified Workspace Files
- Changed files: !`git status --short 2>/dev/null || echo "not a git repo"`

## Execution Steps
1. Identify the target files or directories from `$ARGUMENTS` (or audit the modified files listed above if `$ARGUMENTS` is empty).
2. Invoke `gemini4_security_audit` with `paths` pointing to those workspace-relative paths and `focus="OWASP Top 10, CWE taint flows, authz bypass, injection, SSRF, secrets, dependency CVEs"`.
   - Uses GA **`gemini-4-argon`** (`thinking_level="high"`, `max_output_tokens=32768`, 20-minute timeout — tied **#1 on Endor Labs' 200-task Cursor Agent Security League**, uniquely solving CVE-2021-29488 & CVE-2015-8749), or upgrades automatically to **Gemini 4 Carbon** (#1 AA Intelligence Index v5.0 = 59, 88.2% SEC-bench Pro) when `GEMINI4_FAIRWIND_CARBON_MODEL` is set.
3. Return a crisp executive summary table (`Severity | CWE | File:Line | Exploit Vector | Concrete Patch`) to the parent session without dumping raw file contents.
