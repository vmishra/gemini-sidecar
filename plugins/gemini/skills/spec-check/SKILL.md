---
name: spec-check
description: Check whether code implements a specification - a PDF, Markdown or text spec in the repo, or a URL such as an RFC or API doc - requirement by requirement, with path:line evidence.
argument-hint: "<spec.pdf | spec.md | https://...> [paths...] [--focus <area>]"
disable-model-invocation: true
allowed-tools: Glob Grep mcp__plugin_gemini_gemini4__gemini4_spec_check
---

# Spec compliance check with Gemini

Request: $ARGUMENTS

1. The first argument is the spec: a workspace file (`.pdf`, `.md`, `.txt` and similar) or an `https://` URL. Gemini reads PDFs natively, including tables and diagrams.
2. Code paths: use the remaining paths in the request. If there are none, find the implementing code with Grep and Glob, using names and terms from the request. Don't read file bodies yourself.
3. If the request contains `--focus <area>`, pass it as `focus`.
4. Call `gemini4_spec_check` with `spec` and `paths`.
5. Present the table, then the gaps that matter most. For anything marked Missing or Contradicts, read the cited lines to confirm before proposing a fix. Change nothing until the user agrees.
