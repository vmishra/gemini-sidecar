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

We ran the same six tasks through the MCP server on both models, with identical inputs, on 11 November 2026. Carbon figures are the **median of three runs** with 2.4.4 (medium thinking, streamed). The previous model was run once.

| Task | `gemini-4-argon` (high thinking, 1 run) | `gemini-4-carbon` (median of 3) | Carbon's three runs |
|---|---|---|---|
| `/gemini:security-audit`, 3 files, 4,278 lines | 563 s, $0.97, 5 findings | 443 s, $0.93, 6 findings | 353 / 443 / 603 s |
| `/gemini:review`, diff with 2 planted bugs | 41 s, $0.03, both caught | 100 s, $0.03, both caught in every run | 30 / 100 / 324 s |
| `/gemini:analyze --deep`, 106 files, 259K tokens | 43 s, $1.07 | 79 s, $1.11 | 72 / 79 / 104 s |
| `/gemini:spec-check`, RFC 6585 by URL | 119 s, $0.42 | 112 s, $0.34 | 35 / 112 / 148 s |
| `/gemini:refactor`, a 2-file feature | 215 s, $0.39 | 308 s, $0.59 | 235 / 308 / 520 s |
| `/gemini:map`, 2 directories | 121 s, $0.36 | 179 s, $0.35 | 103 / 179 / 196 s |
| **Six tasks** | **18 min, $3.24** | **20 min, $3.33** | |

Times are wall clock for the whole command. Costs are at Vertex AI global list prices ($4 / $0.20 / $20 per 1M tokens for both models). Google's introductory pricing halves them through 30 November 2026.

### What the numbers say

- **Audits are faster and find more.** The median Carbon audit took 443 s, against 563 s for the previous model, and reported 6 findings to 5 (7 in one run).
  - Every audit run found the same high-severity code-execution issue.
  - The previous model's run also found a confirmed High issue: a `workspace_root` that steps into `.git`.
  - A Carbon audit at high thinking found another confirmed High issue that no other run reported: a `.git` file that redirects reviews to another repository.
  - We reproduced all three with proofs of concept, and all are fixed in 2.4.1. For security-critical code, set `GEMINI4_PRO_THINKING_LEVEL=high`, or audit with more than one model.
- **Spec checks are faster and cheaper.** Median 112 s and $0.34. From 2.4.1 the server sends the page's text rather than its HTML, so the input is half as large.
- **Carbon's latency varies a lot.** The same 1,200-token review took 30 s in one run and 324 s in another, with the same answer. Single runs mislead, which is why the Carbon column reports medians.
- **Streaming removed the re-reads.** Carbon writes long answers in segments, and each segment re-reads the prompt. Before 2.4.4, a non-streamed segment held 32,768 output tokens and the refactor re-read its prompt several times (48,458 input tokens for 7,845 tokens of files). Streamed segments hold 65,536, so the same refactor now reads its prompt once. Measured before and after on the same task, cost fell from $0.95 to $0.59 and time from 624 s to 308 s.
- **Thinking level matters.** At high thinking, Carbon took 232 s for the review and 21 minutes for the spec check. 2.4.3 and later use medium for every task; `GEMINI4_PRO_THINKING_LEVEL` changes it.

### What broke on the old settings

Before 2.4.0, the plugin gave every model a 32K output budget and high thinking. On those settings Carbon failed two tasks:
- The audit spent the whole budget on reasoning and returned nothing.
- The refactor stopped with `finishReason=CONTINUATION`, which the plugin did not handle.

2.4.0 added continuation support and a larger output budget, and both tasks complete now.

## Method

- **Inputs.** The gemini-sidecar repository at commit `df3397f` (audit, spec check, map) and [google/santa-tracker-web](https://github.com/google/santa-tracker-web) at commit `7b7b0d17c` (review, deep analysis, refactor). The review applies a two-line patch that removes an origin check and changes a timeout from 10 s to 1 s.
- **Same prompts.** Each task calls the MCP tool exactly as the slash command does. Only the model differs.
- **One call at a time.** Runs were sequential on a GCE VM in `asia-south1`, against the Vertex AI `global` endpoint.
- **Versions.** Previous model: plugin 2.3.8 settings. Carbon: 2.4.4 (medium thinking, streamed continuation).
- **Repeats.** Carbon: three runs per task, median reported, with every run listed. One refactor run hit an expired Vertex access token during a long answer; 2.4.5 refreshes the token, and that run was repeated. The previous model: one run per task.
- **Objective checks.** Findings are counted from the audit table; review checks whether each planted bug is named and whether the verdict blocks the change; spec checks count requirements by status. Audit findings were then verified by hand and with proofs of concept.
- **Since the runs.** From 2.4.1, the server fetches spec URLs itself rather than letting the model fetch them, so the spec-check input differs slightly from the measured run.

The [CHANGELOG](../CHANGELOG.md) lists the security fixes that came out of these audits.
