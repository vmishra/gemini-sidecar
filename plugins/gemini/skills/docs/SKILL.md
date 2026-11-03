---
name: docs
description: Write or refresh docstrings and documentation for the given code with Gemini, staged for review. Behaviour is not changed.
argument-hint: "<paths...> [what to document]"
disable-model-invocation: true
allowed-tools: Read mcp__plugin_gemini_gemini4__gemini4_long_decode_refactor
---

# Generate documentation with Gemini

Request: $ARGUMENTS

1. Paths come from the request; they are required. Include `README.md` in `paths` only if the request asks for README changes.
2. Call `gemini4_long_decode_refactor` with `mode: "docs"`, the `paths`, and a `spec` that restates what to document and the docstring style already used in the project.
3. For each staged file, compare it with the original (Read both) and confirm that only comments and docstrings changed. Flag any code change. Ask the user before applying.
