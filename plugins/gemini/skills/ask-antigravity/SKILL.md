---
name: ask-antigravity
description: Get an independent second opinion from Gemini (through the Antigravity CLI when enabled) on the current plan, design, or change.
argument-hint: "[question] [paths...]"
disable-model-invocation: true
allowed-tools: mcp__plugin_gemini_gemini4__ask_antigravity
---

# Second opinion from Gemini / Antigravity

Request: $ARGUMENTS

1. Build the `prompt`. If there is a plan or design under discussion in this conversation, summarize it faithfully (goal, approach, key decisions, open risks) and append the user's question. If the request is empty, ask Gemini to critique that plan.
2. Pass the relevant files or directories as `paths` (from the request or from the plan). Do not paste file contents into the prompt.
3. Call `ask_antigravity`.
4. Present the critique, then state which points you accept and which you disagree with, and why. Do not change the plan without the user's agreement.
