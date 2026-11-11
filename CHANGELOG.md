# Changelog

## 2.4.4 (2026-11-11)

### Performance
- `gemini-4-carbon` calls are streamed (`streamGenerateContent`). A streamed segment carries up to 65,536 output tokens, twice the non-streamed limit, so long answers need half as many continuation hops. Each hop re-reads the prompt and is billed for it. On a measured 2-file refactor, input fell from 48,458 to 7,845 tokens, time from 624 s to 497 s, and cost from $0.95 to $0.69 at Vertex list price.

## 2.4.3 (2026-11-11)

### Changed
- `gemini-4-carbon` uses medium thinking for every task, audits included, and in the gateway's All-Gemini main conversation. Set `GEMINI4_PRO_THINKING_LEVEL=high` to raise it, for example for an audit of security-critical code: in our runs, a Carbon audit at high thinking found one more confirmed high-severity issue. A pinned `gemini-4-argon` keeps high thinking.
- Benchmarks and the README report the medium-thinking Carbon audit: 762 s and $1.49 for 4,278 lines, with 7 findings.

## 2.4.2 (2026-11-11)

### Security
- File collection fails closed when a folder is inside a git working tree but git cannot be used safely: a `.git` file that points elsewhere, git older than 2.31 with filters configured, or a failing git. Previously it walked the folder without `.gitignore` filtering, which could pick up a user's ignored local files. The ignore check treats every file as ignored in that case. Set `GEMINI4_INCLUDE_IGNORED=1` to read anyway.
- Spec pages are reduced to text with the standard library's HTML parser instead of a regular expression that could take quadratic time on a hostile page.

### Added
- [docs/benchmarks.md](docs/benchmarks.md): Google's published Gemini 4 Carbon results, and measured runs of six sidecar commands on Carbon and on the previous Pro model, with the method.
- README: measured table updated with Carbon runs, and all costs at Vertex AI list prices.

## 2.4.1 (2026-11-11)

### Security
These issues were found by the security audits in our model benchmark. Each was reproduced with a proof of concept before it was fixed, and each fix has a regression test.
- **Code execution from a hostile repository (high).** A repository could define a git filter driver whose name contains `=`. The neutralising `-c filter.<name>.clean=cat` was split by git at the first `=`, so the repository's own filter stayed active and ran during `/gemini:review`. Overrides now go through `GIT_CONFIG_COUNT` / `GIT_CONFIG_KEY_n` / `GIT_CONFIG_VALUE_n`, which keep key and value apart. If git is older than 2.31, the server refuses to run git rather than risk it. Reported by all four models in the benchmark.
- **Credential disclosure through `workspace_root` (high).** A narrowed root such as `.git`, `.ssh` or `.aws` made files inside it look ordinary, so `.git/config` could be sent, including any credentials embedded in a remote URL. A narrowed root may no longer sit inside a git or credential directory.
- **Another repository's code disclosed through a `.git` file (high).** A folder containing `.git` as a file (`gitdir: /path/to/other-repo/.git`) made `/gemini:review` diff and send that other repository. A git directory is now trusted only when it lies inside the working tree, or is a linked worktree or submodule that points back to it.
- **Spec URLs are fetched by the server.** Previously Gemini fetched the page with its URL context tool, in the same call as the workspace code. The server now fetches the page itself (`https` only, public addresses only, every redirect re-checked, size-capped) and no fetch tool is enabled.
- **Antigravity hand-off.** Agent and tool configuration (`.gemini/`, `.claude/`, `.mcp.json`, `AGENTS.md` and similar) is never copied into the temporary directory `agy` runs in. The prompt passed to `agy` is redacted like every other prompt.
- **Test logs.** `/gemini:test-triage` applies the same checks as file reads: regular files only, nothing inside a git directory, and a git-ignored file only if it has a log suffix.
- **Workspace roots.** Parents of the home directory, top-level directories and shared temp directories are refused, as well as `/` and the home directory itself.

### Changed
- Thinking level on `gemini-4-carbon`: `medium` for reviews, refactors, maps and spec checks, `high` for security audits. In measured runs, Carbon at medium reviewed the planted-bug diff in 21 s (232 s at high) and finished the RFC spec check in 5 minutes (21 at high).
- Cost reports, gateway budget caps and docs use Vertex AI global list prices from the Cloud Billing catalog: `gemini-4-carbon` $4 / $0.20 / $20, `gemini-3.8-flash` $1.50 / $0.15 / $7.50, `gemini-3.5-flash-lite` $0.30 / $0.03 / $2.50 per 1M tokens. Google's introductory pricing halves Carbon through 30 November 2026 and Flash through 31 December 2026, so reported costs are an upper bound until then. Gateway: the `claude-opus-5-5` cache-read price is now $0.20.

## 2.4.0 (2026-11-11)

### Changed
- The Pro model is now `gemini-4-carbon`, used for audits, reviews, refactors, spec checks, `/gemini:map`, `ask-antigravity` and `analyze --deep`. List pricing is the same as before: $2 / $0.10 / $10 per 1M tokens, then $4 / $0.20 / $20 from 1 December 2026. To keep the previous model, set `primary_model` (or `GEMINI4_PRIMARY_MODEL`) to `gemini-4-argon`. It still gets high thinking and correct cost reporting.
- Gateway: the All-Gemini main conversation, the auto router's complex tier and opt-in failover use `gemini-4-carbon`.

### Added
- Long decode. When Carbon reaches the end of one response segment, it returns `finishReason=CONTINUATION` with a continuation token. The server now resends the same request with the token until the answer is complete, up to 8 segments (`GEMINI4_MAX_CONTINUATIONS`), and sums usage and cost across segments. Vertex AI calls use `v1beta1`, which is required for continuation.
- `GEMINI4_PRO_THINKING_LEVEL` (`low`, `medium` or `high`) overrides the thinking level for the Pro model.

### Fixed
- Carbon thinks longer than Argon, and its thinking counts toward the output budget. Under the old 32K budget an audit could spend it all on reasoning and return nothing. Carbon now gets a larger budget, and an empty `MAX_TOKENS` answer is retried once with twice the room.
- Gateway: Carbon's output per turn is capped at one segment (32,768 tokens), and a `CONTINUATION` stop maps to `max_tokens`, so All-Gemini sessions never see an error for it.

## 2.3.8 (2026-11-05)

### Fixed
- `/gemini:deps` checks large manifests in parallel batches of about a dozen packages and merges the results, with vulnerable packages first. A 50-package `package.json` went from about 4 minutes, with intermittent `TOO_MANY_TOOL_CALLS` failures, to about a minute. A batch that still hits the tool-call limit is split and retried, and any batch that cannot be checked is listed instead of silently dropped.
- Usage accounting is thread-safe.

## 2.3.7 (2026-11-05)

### Added
- `/gemini:analyze --fast` uses the Flash-Lite model. On a 260K-token question it answered in about 4 seconds, compared with about a minute on Flash.

## 2.3.6 (2026-11-05)

### Security
- Inside a git repository, file listing no longer falls back to walking the disk when `git ls-files` fails or times out. The walk would have included untracked files that `.gitignore` excludes; the call now stops with a clear error instead.

## 2.3.5 (2026-11-05)

### Fixed
- Large repositories no longer go over Gemini's input limit. The context budget is counted in estimated tokens instead of characters (a flat chars/4 rule undercounted inline SVG, markup and data by up to 3x, so a whole-repository call could be rejected by the API). The estimator is fitted to `countTokens` results across code, markup, data and docs. The default budget is 750K estimated tokens.
- When a scope does not fit, the important files are read first:
  - source code comes first, then data and markup, then translation catalogs, lockfiles, changelogs, licenses, generated code (`zz_generated*`, `*.pb.go`, `*_pb2.py`) and SVG
  - within each tier, sibling directories take turns, so a large folder cannot take the whole budget
  - minified or very dense files, and any single file over 1/12 of the budget, are placed after everything else
- Tracked `build/`, `dist/` and `vendor/` directories are read (at low priority) instead of skipped; some projects keep real source there. `node_modules` and similar dependency trees are still never read.
- Audio, video, font, design and ML model files are recognised as binary without being opened.

### Performance
- A whole-repository call on a ~32K-file repository went from 41 s to under 3 s before the model call. Ignore rules are taken from git in one call instead of checking every path, files that cannot fit are skipped without being read, and collection stops once the budget is effectively full.
- Globs are matched against git's file list instead of walking the disk, so `**/*.js` never traverses `node_modules`.
- `/gemini:analyze` uses a 400K-token budget by default (`GEMINI4_ANALYZE_MAX_TOKENS`): questions need the relevant code, and input time grows with size.

### Changed
- A request over the model's token limit now returns an actionable message.
- `/gemini:map` and `/gemini:security-audit` go ahead when the estimate shows files left out, instead of narrowing paths by hand.

## 2.3.4 (2026-11-04)

### Security
- Secret-assignment redaction:
  - quoted values stop only at their matching quote
  - an assignment that shares a line with an earlier one (`token_type=Bearer,api_key="..."`) is no longer skipped
  - the skip-ahead optimisation is proven equivalent to a simple reference implementation by a randomised test

## 2.3.3 (2026-11-04)

### Security
- Secret-assignment redaction:
  - covers base64 values with `=` padding again (a 2.3.2 regression)
  - covers hyphenated names such as `api-key` and `X-Api-Key`
  - bounds the work per match, so adversarial input can't make the scan quadratic

## 2.3.2 (2026-11-04)

### Security
- Secret-named assignments are redacted by a linear-time scanner instead of regular expressions. This fixes a 2.3.1 regression where values over 512 characters or variable names with long prefixes were not redacted, and removes the remaining slow-regex input.

## 2.3.1 (2026-11-04)

### Security
- Review: only known binary formats are skipped. Any other file is reviewed as text, even if it contains NUL bytes, and is flagged, so inserting a NUL can't hide a change.
- Secret-assignment redaction uses bounded patterns (no catastrophic backtracking on long identifiers).
- Installer: settings are written through an unpredictable, exclusively created temp file, so a planted `.tmp` symlink can't redirect the write.

## 2.3.0 (2026-11-04)

Hardening from a pre-release adversarial security review.

### Security
- git runs with repository-controlled command execution disabled: hooks, fsmonitor, external diff, textconv, filter drivers, pager and embedded bare repositories. Previously, a malicious repository delivered with its `.git` folder could make `/gemini:review` run a command.
- Review diffs are forced to text, so `.gitattributes` can't hide a change.
- Gitignored files are skipped even when named explicitly (`GEMINI4_INCLUDE_IGNORED=1` restores the old behaviour). Credential folders and bare repositories are never read.
- Redaction now also covers AWS secret keys, GitLab, npm and Hugging Face tokens, Google client secrets and refresh tokens, Stripe test keys, PGP private keys, secret-named literals, and passwords containing `/` or `@` inside URLs. Typed questions and specs are redacted too.
- Log and key scanning run in linear time, so very long lines can't stall the server.
- The MCP server survives malformed messages.
- Staged files that target CI, hooks or agent config are flagged. Write conflicts no longer abort a run.
- Gateway:
  - concurrent connections are capped, with a shorter idle timeout
  - the token file is refused if it's a symlink, readable by others, or shorter than 32 characters
  - non-finite budget values are refused, and missing usage is charged at the reservation
  - Anthropic passthrough reserves budget against the real `max_tokens`
  - relayed headers with line breaks are dropped
  - deeply nested JSON gets a 400
- Gateway failover to Google on an Anthropic 429/529 is now opt-in (`GEMINI4_FAILOVER_TO_GEMINI=1`).
- Installer: Python runs isolated (`-I`), so a module planted in the current directory can't be imported. It refuses to write through symlinks, writes settings atomically, and detects an existing Codex entry in any TOML spelling.
- The read guard no longer echoes file names, which are attacker-controlled. Skills scope `Read` to the project.
- CI actions and the Python 3.9 container are pinned by digest, and Dependabot is enabled.

### Changed
- Cost reports include tokens from pages read by URL context.
- The gateway sends its first SSE keep-alive as soon as the stream opens.
- README: new security and privacy section, animated replays for five commands, and corrected claims.

## 2.2.1 (2026-11-04)

### Security
- The read guard's `suggest` mode no longer returns a permission decision. It only adds advice, so your permission rules still decide whether a read is allowed.

## 2.2.0 (2026-11-04)

### Added
- `estimate_only` on the analyze, security audit, refactor and spec-check tools: files, tokens, estimated cost and typical time, without calling Gemini. The audit, refactor and map commands preview automatically for large scopes.
- Optional large-read guard for Claude Code (`GEMINI_SIDECAR_READ_GUARD=suggest|block`, off by default). It points whole-file reads of large files to `/gemini:analyze`; partial reads always pass.
- README section "When not to use it".

### Changed
- Test logs keep their evidence. Every failure, error, traceback and `file:line` line in a large log is kept along with the tail, and dropped line ranges are marked in place. Previously only the tail was kept.
- When the context budget is reached, answers name the files that were left out instead of only counting them.
- Refactor and test generation include an existing file as a style reference.
- Tool descriptions are shorter, and a test now caps the schema footprint. This matters for hosts that load every tool schema on every turn.

## 2.1.1 (2026-11-04)

### Security
- Redact passwords embedded in URLs (`https://user:password@host`, database connection strings) in everything sent to Gemini.
- `/gemini:deps` never forwards URL-style dependency versions, which can carry credentials. They appear as `<url or path>`.

## 2.1.0 (2026-11-04)

### Added
- `/gemini:deps`: checks dependency manifests against live Google Search results (latest versions, CVEs affecting the declared versions, breaking changes) and lists its sources. Common manifest formats are parsed exactly, so declared versions are never misread.
- `/gemini:spec-check`: checks code against a PDF, Markdown or text spec in the repository, or a URL, requirement by requirement.
- `/gemini:see`: debugs from screenshots or short screen recordings alongside the source code.
- `/gemini:map`: writes an `ARCHITECTURE.md` onboarding guide for the repository, staged for review.
- MCP tools `gemini4_check_dependencies`, `gemini4_spec_check` and `gemini4_visual_debug`, plus an `architecture` mode for `gemini4_long_decode_refactor`.

### Fixed
- README: the prefix-free example now uses `/analyze`. Bare `/review` runs Claude Code's built-in review.

## 2.0.0 (2026-11-03)

First release as `gemini-sidecar` (previously `gemini4-harness-kit`).

### Added
- Claude Code plugin `gemini` with nine commands: `/gemini:analyze`, `security-audit`, `review`, `refactor`, `test-gen`, `test-triage`, `docs`, `ask-antigravity`, `status`.
- MCP tools `gemini4_review_diff` and `gemini4_triage_failures`.
- Subagents `gemini-explorer` and `gemini-implementer`.
- Real token usage and cost reporting, from the API's usage data.
- Offline test suite for the MCP server and the gateway.

### Security
- File reads are confined to the workspace. They follow `.gitignore`, never read secret files or `.git/`, and redact common token formats.
- Generated files are written only to `.gemini4-staging/`. Paths into `.git/` and symlinked staging folders are refused.
- Gateway: a token is required on every endpoint except `/health`, browser requests are rejected (`Origin`/`Host` checks), request size is limited, and the API key is sent in a header.
- The Antigravity CLI runs on redacted copies of the approved files, with a scrubbed environment.
- Six issues found by running the security audit on this repository were fixed.

### Changed
- Codex CLI and Cursor integrate through the MCP server.
- The gateway forwards Anthropic requests unchanged and never reroutes a conversation based on prompt content.

### Removed
- The claude-code-router worker, the Codex profile and agent files, and the OpenAI-compatible gateway endpoints. They did not work as documented.
