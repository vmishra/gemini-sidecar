# Benchmarks

`gemini-4-carbon` replaced `gemini-4-argon` as the Pro model in 2.4.0. This page covers what Google publishes about Carbon, and what we measured when we ran the sidecar's own commands on both models.

## Google's published results for Gemini 4 Carbon

Quoted from Google's announcements. We have not reproduced them.

| Benchmark | What it measures | Carbon |
|---|---|---:|
| Artificial Analysis Intelligence Index v5.0 | General capability composite | 59 (ranked #1) |
| SEC-bench Pro | Finding vulnerabilities | 88.2% |
| ExploitGym | Exploiting vulnerabilities | 54.8% |
| CWE-bench (Collinear) | Turning findings into working fixes | 71.0% |
| WebDev Arena | Web development, human preference | 1768 Elo (#4, +89) |
| Gray Swan Indirect Prompt Injection | Attack success rate (lower is better) | 0.0% |
| Terminal-Bench 4.0 | Successful cheating (lower is better) | 0.0% |

Google also reports that Carbon ranks #1 on CursorBench 4.0, Perplexity WANDR and Zapier AutomationBench, at more than 2x lower cost per task than the next best external model. It also notes that Carbon "uses more tokens than Argon to explore thoroughly, reason deeply, and run extended verification loops."

Sources: [Introducing Gemini 4 Carbon](https://blog.google/innovation-and-ai/models-and-research/gemini-models/introducing-gemini-4-carbon/) (28 October 2026), [Gemini 4 Carbon is now available](https://blog.google/innovation-and-ai/models-and-research/gemini-models/gemini-4-carbon-now-available/) (10 November 2026).

## Measured: the sidecar's commands on Carbon and on Argon

We ran the same six tasks through the MCP server on both models, with identical inputs, on 11 November 2026.

| Task | `gemini-4-argon` (high thinking) | `gemini-4-carbon` (2.4.1 defaults) |
|---|---|---|
| `/gemini:security-audit`, 3 files, 4,278 lines | 563 s, $0.97, 5 findings (2 High) | 516 s, $1.66, 7 findings (3 High) |
| `/gemini:review`, diff with 2 planted bugs | 41 s, $0.03, both caught, DO NOT SHIP | 21 s, $0.02, both caught, DO NOT SHIP |
| `/gemini:analyze --deep`, 106 files, 259K tokens | 43 s, $1.07 | 65 s, $1.12 |
| `/gemini:spec-check`, RFC 6585 by URL | 119 s, $0.42 | 322 s, $0.49 |
| `/gemini:refactor`, a 2-file feature | 215 s, $0.39 | 624 s, $0.95 |
| `/gemini:map`, 2 directories | 121 s, $0.36 | 127 s, $0.35 |

The Carbon column uses the 2.4.1 defaults: high thinking for audits, medium for everything else. Times are wall clock for the whole command. Costs are at Vertex AI global list prices ($4 / $0.20 / $20 per 1M tokens for both models). Google's introductory pricing halves them through 30 November 2026.

### What the numbers say

- **Audits find more, and different things.** Carbon reported 7 findings to Argon's 5.
  - Both runs found the same high-severity code-execution issue.
  - Each run also found one confirmed high-severity issue the other missed. Carbon found a `.git` file that redirects reviews to another repository. Argon found a `workspace_root` that steps into `.git`.
  - We reproduced all three with proofs of concept, and all are fixed in 2.4.1. Running audits on more than one model is worth it for code that matters.
- **Reviews are faster.** With medium thinking, the planted-bug review took half the time and caught both bugs.
- **Long outputs take longer and cost more.** Carbon writes past one response with continuation tokens. Each segment re-reads the prompt and is billed for it, so refactors and audits show more input tokens than the files contain. This is why the Carbon refactor read 48K tokens where Argon read 8K. Google notes Carbon uses more tokens than Argon by design.
- **Thinking level matters a lot.** At high thinking, Carbon took 232 s for the same review and 21 minutes for the spec check. That is why 2.4.1 uses medium for everything except audits. You can change it with `GEMINI4_PRO_THINKING_LEVEL`.

### What broke on the old settings

Before 2.4.0, the plugin gave every model a 32K output budget and high thinking. On those settings Carbon failed two tasks:
- The audit spent the whole budget on reasoning and returned nothing.
- The refactor stopped with `finishReason=CONTINUATION`, which the plugin did not handle.

2.4.0 added continuation support and a larger output budget, and both tasks complete now.

## Method

- **Inputs.** The gemini-sidecar repository at commit `df3397f` (audit, spec check, map) and [google/santa-tracker-web](https://github.com/google/santa-tracker-web) at commit `7b7b0d17c` (review, deep analysis, refactor). The review applies a two-line patch that removes an origin check and changes a timeout from 10 s to 1 s.
- **Same prompts.** Each task calls the MCP tool exactly as the slash command does. Only the model differs.
- **One call at a time.** Runs were sequential on a GCE VM in `asia-south1`, against the Vertex AI `global` endpoint.
- **Single runs.** These are single runs, not averages. Model latency varies: the Carbon audit took 516 s at high thinking in one run and 762 s at medium in another.
- **Objective checks.** Findings are counted from the audit table; review checks whether each planted bug is named and whether the verdict blocks the change; spec checks count requirements by status. Audit findings were then verified by hand and with proofs of concept.
- **Since the runs.** From 2.4.1, the server fetches spec URLs itself rather than letting the model fetch them, so the spec-check input differs slightly from the measured run.

The [CHANGELOG](../CHANGELOG.md) lists the security fixes that came out of these audits.
