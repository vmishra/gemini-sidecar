---
name: review
description: Pre-commit review of the current git changes by Gemini. The server runs git diff itself, so the diff does not enter this conversation.
argument-hint: "[base-ref] [--staged] [--fast]"
disable-model-invocation: true
allowed-tools: mcp__plugin_gemini_gemini4__gemini4_review_diff Bash(git diff --stat HEAD)
---

# Review changes with Gemini

Request: $ARGUMENTS

Current change summary:
!`git diff --stat HEAD`

1. Base ref: the first argument that is not a flag, or `HEAD` (uncommitted changes) if none. For a branch review, use something like `main` or `origin/main`.
2. `--staged` sets `staged_only: true`. `--fast` sets `model_tier: "flash"`; the default is `"pro"`.
3. Call `gemini4_review_diff`.
4. Relay the issues and the verdict. If the verdict is not SHIP, offer to fix the listed issues, but do not edit anything until the user agrees.
