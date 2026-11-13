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

## Measured: the sidecar's commands on four Gemini models

We ran the same six tasks through the MCP server on four Gemini models, with identical prompts and files, on 13 November 2026. Each model ran three times, and the figures are medians. Costs are at Vertex AI global list prices. Output tokens include thinking. Every model finished every task in one API request.

| Model | Thinking | Six tasks | Cost | Input / output tokens | of which thinking | Audit caught the code-execution bug | Review caught both planted bugs |
|---|---|---:|---:|---:|---:|---|---|
| Gemini 4 Carbon | medium | 26.3 min | $3.42 | 436K / 84K | 63K | 3 of 3 | 3 of 3 |
| Gemini 4 Argon | high | 19.5 min | $3.23 | 436K / 74K | 53K | 2 of 3 | 3 of 3 |
| Gemini 3.8 Flash | medium | 8.1 min | $0.74 | 438K / 82K | 66K | 0 of 3 | 3 of 3 |
| Gemini 3.5 Flash | medium | 2.5 min | $0.50 | 438K / 42K | 28K | 0 of 3 | 3 of 3 |

Per task, median of three runs:

| Task | Gemini 4 Carbon | Gemini 4 Argon | Gemini 3.8 Flash | Gemini 3.5 Flash |
|---|---|---|---|---|
| Security audit, 4,278 lines | 427 s, $0.88, 6 findings | 404 s, $0.92, 5 findings | 161 s, $0.26, 0 findings | 38 s, $0.13, 0 findings |
| Review, 2 planted bugs | 135 s, $0.03 | 23 s, $0.03 | 19 s, $0.01 | 10 s, $0.02 |
| Deep analysis, 106 files | 77 s, $1.11 | 56 s, $1.07 | 29 s, $0.07 | 16 s, $0.08 |
| Spec check, RFC 6585 | 208 s, $0.36, 6 met / 5 partial | 121 s, $0.30, 7 met / 3 partial | 35 s, $0.05, 4 met / 1 partial | 24 s, $0.07, 7 met / 0 partial |
| Refactor, 2-file feature | 429 s, $0.71 | 380 s, $0.51 | 204 s, $0.26 | 34 s, $0.14 |
| Architecture map | 303 s, $0.32 | 186 s, $0.40 | 40 s, $0.08 | 29 s, $0.06 |

### What the numbers say

- **Use a Pro model for audits.** The audited commit contains a confirmed high-severity code-execution bug: a git filter name containing `=`, fixed in 2.4.1.
  - Carbon flagged it in all three runs and Argon in two.
  - Both Flash models missed it every time, and reported no vulnerabilities at all.
  - This is why `/gemini:security-audit` always runs on the Pro model.
- **Flash is fast and cheap for questions and reviews.** All four models caught both planted bugs in every review run. 3.5 Flash finished all six tasks in 2.5 minutes for $0.50.
- **Carbon thinks the most and takes the longest.** Across the six tasks it wrote 84K output tokens, 63K of them thinking, against Argon's 74K. Google notes Carbon uses more tokens than Argon by design. With streaming (2.4.4), every task needed only one request.
- **Carbon's latency varies a lot.** One spec-check run took 1,376 s against a median of 208 s. The four models ran side by side for this comparison. On 11 November, when Carbon ran alone, its six-task median was 20 minutes rather than 26.
- **Thinking level matters.** At high thinking, Carbon took 232 s for the review and 21 minutes for the spec check in an earlier run. Medium is the default from 2.4.3; `GEMINI4_PRO_THINKING_LEVEL` changes it.

### What broke on the old settings

Before 2.4.0, the plugin gave every model a 32K output budget and high thinking. On those settings Carbon failed two tasks:
- The audit spent the whole budget on reasoning and returned nothing.
- The refactor stopped with `finishReason=CONTINUATION`, which the plugin did not handle.

2.4.0 added continuation support and a larger output budget, and both tasks complete now.

## Method

- **Inputs.** The gemini-sidecar repository at commit `df3397f` (audit, spec check, map) and [google/santa-tracker-web](https://github.com/google/santa-tracker-web) at commit `7b7b0d17c` (review, deep analysis, refactor). The review applies a two-line patch that removes an origin check and changes a timeout from 10 s to 1 s.
- **Same prompts.** Each task calls the MCP tool exactly as the slash command does. Only the model differs.
- **One call at a time.** Runs were sequential on a GCE VM in `asia-south1`, against the Vertex AI `global` endpoint.
- **Versions and settings.** Plugin 2.4.5. Carbon at medium thinking (the default), Argon at high (its default before 2.4.0), both Flash models at medium.
- **Repeats.** Three runs per model per task; medians reported.
- **Concurrency.** The four models ran in parallel, each on its own copy of the repositories; runs for one model were sequential.
- **Objective checks.** Audits: whether the confirmed code-execution bug is flagged as High, plus the number of findings. Reviews: whether each planted bug is named and the verdict blocks the change. Spec checks: requirements by status. Findings were verified by hand and with proofs of concept.
- **Since the runs.** From 2.4.1, the server fetches spec URLs itself rather than letting the model fetch them, so the spec-check input differs slightly from the measured run.

The [CHANGELOG](../CHANGELOG.md) lists the security fixes that came out of these audits.
