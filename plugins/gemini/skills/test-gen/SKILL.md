---
name: test-gen
description: Generate tests for the given source files with Gemini, staged for review, then optionally apply and run them.
argument-hint: "<paths...> [extra instructions]"
disable-model-invocation: true
allowed-tools: Glob Read mcp__plugin_gemini_gemini4__gemini4_long_decode_refactor
---

# Generate tests with Gemini

Request: $ARGUMENTS

1. Source paths come from the request; they are required. Add the existing test directory (for example `tests/`, `test/`, `__tests__/`, or `*_test.go` siblings) to `paths`, so Gemini follows the project's framework and conventions. Find it with Glob.
2. Call `gemini4_long_decode_refactor` with `mode: "tests"`, those `paths`, and a `spec` naming the files to cover plus any extra instructions from the request.
3. List the staged test files. Ask the user before applying. On approval, copy them into place, run only the new tests, and report pass or fail. If tests fail, decide whether the test or the code is wrong before changing anything.
