---
name: status
description: Show the Gemini plugin configuration, credentials status, and token usage and estimated cost for this session.
disable-model-invocation: true
allowed-tools: mcp__plugin_gemini_gemini4__gemini4_status
---

Call `gemini4_status` and show the result as is. If the backend is not configured, explain the two options: a Gemini API key through `/plugin configure gemini@gemini4-harness-kit` or `GEMINI_API_KEY`, or Vertex AI through `GOOGLE_GENAI_USE_VERTEXAI=true`, `GOOGLE_CLOUD_PROJECT`, and `gcloud auth application-default login`.
