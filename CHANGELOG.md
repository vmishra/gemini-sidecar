# Changelog

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
