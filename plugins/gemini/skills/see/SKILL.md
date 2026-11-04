---
name: see
description: Debug from a screenshot or a short screen recording - Gemini watches it next to your source code and points to the components and lines responsible.
argument-hint: "<screenshot.png | recording.mp4 ...> [code paths...] [what is wrong]"
disable-model-invocation: true
allowed-tools: Glob mcp__plugin_gemini_gemini4__gemini4_visual_debug
---

# Visual debugging with Gemini

Request: $ARGUMENTS

1. Media: the image or video files in the request (`.png`, `.jpg`, `.webp`, `.mp4`, `.mov`, `.webm`). They must be inside the project. If the user pasted an image into the chat instead, ask them to save it in the project (for example `screens/bug.png`) and pass the path. The limit is about 14 MB per call, so trim long recordings.
2. Code paths: use any paths in the request. Otherwise pick the frontend directories most likely to render what is shown, using Glob.
3. Question: the rest of the request. If there is none, use "What is wrong on screen, and which code causes it?".
4. Call `gemini4_visual_debug` with `media`, `question` and `paths`.
5. Relay what Gemini saw, the cause, and the cited lines. Read those lines to confirm before proposing the fix. Change nothing until the user agrees.
