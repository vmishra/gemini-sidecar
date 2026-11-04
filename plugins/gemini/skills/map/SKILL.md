---
name: map
description: Read the whole repository and write an ARCHITECTURE.md onboarding guide - components, data flow, how to run and test, where to start - staged for review.
argument-hint: "[paths...] [audience or emphasis]"
disable-model-invocation: true
allowed-tools: Read(./**) mcp__plugin_gemini_gemini4__gemini4_long_decode_refactor
---

# Repository map with Gemini

Request: $ARGUMENTS

1. Paths: use any paths in the request. Otherwise use `"."` (the whole repository; .gitignore and secret files are skipped automatically).
2. Build a `spec` from the request: who the guide is for and anything to emphasize. If the request says nothing, use "Onboarding guide for a new engineer".
3. For a large repository, call first with `estimate_only: true` and share the expected cost and time. Then call `gemini4_long_decode_refactor` with `mode: "architecture"`, `paths` and `spec`. If the estimate says some files were left out, go ahead anyway: the server reads source code first, spreads the budget across every directory, and leaves translations, lockfiles, generated code and bulky assets for last. Do not narrow the paths by hand unless the user asked for a specific area.
4. Read the staged `ARCHITECTURE.md` and show its outline (the headings), plus anything that looks wrong to you.
5. Ask before copying it to the repository root. If an `ARCHITECTURE.md` already exists, show what would change first.
