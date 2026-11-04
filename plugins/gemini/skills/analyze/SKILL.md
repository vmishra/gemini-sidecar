---
name: analyze
description: Answer a question about a large part of the codebase by having Gemini read the files from disk. Only the answer enters this conversation.
argument-hint: "<question> [paths...] [--deep]"
disable-model-invocation: true
allowed-tools: Glob mcp__plugin_gemini_gemini4__gemini4_analyze_codebase
---

# Analyze the codebase with Gemini

Request: $ARGUMENTS

1. Split the request into a question and any paths (files, directories, or globs). If `--deep` is present, remove it and use `model_tier: "pro"`; otherwise use `"flash"`.
2. If no paths were given, pick the smallest set of top-level directories that can answer the question. Use Glob on the repository layout if needed. Use `"."` only when the question is about the whole repository.
3. Call `gemini4_analyze_codebase` with `question`, `paths`, and `model_tier`. Do not read the files yourself first; avoiding that is the point of this command.
4. Relay the answer. Keep the `path:line` citations and the usage line. If the scope line reports truncation, it names the files that were left out; offer a follow-up question scoped to those files.
