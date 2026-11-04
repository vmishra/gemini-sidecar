---
name: security-audit
description: Security review of files, directories, or the current changes on Gemini, returning findings with CWE IDs and path:line evidence.
argument-hint: "[paths...] [--focus <area>]"
disable-model-invocation: true
allowed-tools: mcp__plugin_gemini_gemini4__gemini4_security_audit Bash(git status --short)
---

# Security audit with Gemini

Request: $ARGUMENTS

Changed files in the working tree:
!`git status --short`

1. Targets: use the paths in the request. If none were given, use the changed files listed above. Ignore deleted files. If there are no changes either, ask the user which directories to audit; do not audit the whole repository by default.
2. If the request contains `--focus <area>`, pass that text as `focus`.
3. If the targets cover more than about 30 files or whole top-level directories, first call `gemini4_security_audit` with `estimate_only: true` and tell the user the expected cost and time. Audits on the pro model can take several minutes. Then call it for real with `paths` (and `focus` if set).
4. Present the findings table as returned. Then give your own short assessment: which findings you agree with after reading the cited lines, and which look like false positives. Read only the cited lines, not whole files. Do not change any code unless the user asks.
