---
name: test-triage
description: Run the test suite, capture the output to a file, and have Gemini root-cause the failures without the log entering this conversation.
argument-hint: "[test command]"
disable-model-invocation: true
allowed-tools: Bash(mkdir -p .gemini4-staging) Bash(tail -n 5 .gemini4-staging/test-output.log) mcp__plugin_gemini_gemini4__gemini4_triage_failures
---

# Triage test failures with Gemini

Request: $ARGUMENTS

1. Test command: use the one in the request. Otherwise infer it from the project: `pyproject.toml` or `pytest.ini` means `pytest`, `package.json` means `npm test`, `go.mod` means `go test ./...`, `Cargo.toml` means `cargo test`. If it is unclear, ask.
2. Run `mkdir -p .gemini4-staging`, then run the command with all output redirected, for example `pytest > .gemini4-staging/test-output.log 2>&1`. Claude Code asks the user to approve the test command. Do not print the log.
3. If the command exits 0, run `tail -n 5 .gemini4-staging/test-output.log`, report that everything passed, and stop.
4. Otherwise call `gemini4_triage_failures` with `log_path: ".gemini4-staging/test-output.log"` and `paths` set to the source and test directories under test.
5. Relay the triage table. Offer to apply the suggested fixes, one failure group at a time, re-running the tests after each.
