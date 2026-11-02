---
name: bulk-test-triage
description: Run test suites and triage failures across large logs in an isolated Gemini 3.8 Flash forked subagent without polluting the main session context.
context: fork
agent: gemini-codebase-explorer
background: false
allowed-tools: Bash(npm test *) Bash(pytest *) Bash(go test *) Bash(cargo test *) Read Grep Glob
disallowed-tools: Write Edit
---

## Current Repository State
- Working tree status: !`git status --short 2>/dev/null || echo "not a git repo"`
- Recent diff summary: !`git diff --stat HEAD 2>/dev/null || echo "no git diff"`

## Triage Instructions ($ARGUMENTS)
1. Run the relevant test suite or inspect failing logs for `$ARGUMENTS` (or the modified packages above if no arguments were passed).
2. Read the failing test files and corresponding source implementations inside this isolated `gemini-3.8-flash` (`133 tok/s`, `$0.75/M`) forked context.
3. Do NOT attempt to edit any files (`Write` and `Edit` are disabled to protect workspace state).
4. Return ONLY a concise (<400 words) root-cause table to the main planner containing:
   - Failing test name & exact `file:line`
   - Minimal reproduction or stack root cause
   - Recommended 1-3 line fix for the main coding agent
