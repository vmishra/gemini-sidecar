# The gateway (optional)

<p align="center">
  <img src="../assets/gateway.svg" alt="Main conversation, subagents and background calls routed to Claude or Gemini models depending on the profile" width="100%" />
</p>

You don't need the gateway to use the `/gemini:` commands. It's for running Claude Code itself on Gemini models.

Claude Code sends three kinds of model requests: your main conversation, its subagents, and small background calls. The gateway is a local server that receives them (Claude Code points at it through `ANTHROPIC_BASE_URL`) and sends each one to the model shown in the diagram above.

- **Hybrid** keeps Claude Opus 5.5 for your conversation and moves the high-volume work to Gemini. It needs an Anthropic API key for the forwarded requests.
- **All-Gemini** runs everything on Gemini and needs only Gemini credentials.

Either way, a conversation stays on one model from start to finish. The one exception is opt-in: with `GEMINI4_FAILOVER_TO_GEMINI=1`, a Hybrid session moves to `gemini-4-argon` for good if Anthropic returns a rate-limit error (429 or 529), and that sends the full conversation to Google. Without the variable, the error is passed back to Claude Code unchanged.

**What the gateway sends.** It forwards complete Claude Code requests to Gemini, without filtering: your messages, the system prompt, files Claude has read and tool output. The path, secret and redaction protections described in the README apply to the `/gemini:` tools, not to the gateway. Use it only where sending the whole session to Google (or Vertex AI in your project) is acceptable.

**Security.** The gateway:
- listens on `127.0.0.1` only
- requires a token of at least 32 characters, read from a `0600` file it refuses to follow through a symlink
- refuses requests with an `Origin` header or a non-local `Host`, which blocks web pages and DNS rebinding
- caps request size and concurrent connections
- allow-lists model names before they reach a URL
- never logs prompt text

Another user on the same machine can't read or use the gateway without the token, but could tie up its connections and interrupt it while they do. Switching models midway would throw away the prompt cache, and Claude and Gemini tool-call histories are not interchangeable.

```bash
# Terminal 1: start the gateway (the first start creates a private token in ~/.config/gemini4/)
export GOOGLE_GENAI_USE_VERTEXAI=true GOOGLE_CLOUD_PROJECT=my-project   # or GEMINI_API_KEY=...
export ANTHROPIC_UPSTREAM_KEY=sk-ant-...                                # Hybrid only
python3 router/gemini4_gateway.py

# Terminal 2: point a project at it and start Claude Code
./install.sh --gateway-profile all-gemini --project ~/code/my-app       # or: hybrid
cd ~/code/my-app && claude
```

Tested end to end with Claude Code on the All-Gemini profile: multi-step read, edit and test tasks completed, subagents ran on `gemini-3.8-flash`, and Gemini's automatic caching showed in the usage data. Limitations:
- Only Claude Code's API (Anthropic Messages) is implemented.
- Gemini replies arrive in one piece rather than streaming word by word.
- Spend caps (`GEMINI4_SESSION_BUDGET_USD`, `GEMINI4_GLOBAL_BUDGET_USD`) are estimates held in memory.

See also: [configuration and troubleshooting](./reference.md).
