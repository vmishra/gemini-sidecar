# Security policy

This project reads source code and sends it to a model API, so we take security reports seriously.

## Reporting a vulnerability

Please report vulnerabilities privately through GitHub: open the **Security** tab of this repository and choose **Report a vulnerability**. Do not open a public issue.

Include what you found, how to reproduce it, and the impact you expect. We aim to acknowledge reports within three working days and to agree a disclosure date with you once a fix is ready.

## In scope

- Reading files outside the workspace, or reading files that should be excluded (secrets, `.git/`, ignored files)
- Secrets reaching the Gemini API despite the filters
- Writing outside `.gemini4-staging/`, or anything that can lead to code execution
- Gateway issues: authentication bypass, cross-origin or DNS-rebinding access, request smuggling into upstream URLs
- Slash commands whose permissions allow more than they need

## Out of scope

- How Google or Anthropic handle data you send to their APIs; see their terms
- Issues that need an attacker who already controls your shell environment or user account

## Design

| Area | Protection |
|---|---|
| File access | Workspace confinement (no absolute paths outside, `..`, or escaping symlinks); home and `/` refused as roots; gitignored files skipped even when named; secret file names and credential folders (`.ssh`, `.aws`, `.kube`, `.docker`, `.git`, bare repos) never read |
| Data sent | Common token formats, private keys, JWTs, URL passwords and secret-named literals redacted from file contents, diffs, logs and typed prompts; media (images, video, PDF) is sent as-is |
| Untrusted repositories | git runs with hooks, fsmonitor, external diff, textconv, filters and pager disabled, embedded bare repositories refused, and diffs forced to text |
| Writes | Only under `.gemini4-staging/<run>/`; `.git` paths, symlinked staging, secret names and `..` refused; CI, hook and agent-config targets flagged |
| Gateway | Loopback only; 32+ character token in a `0600` file (no symlinks); `Origin`/`Host` checks against browsers and DNS rebinding; size and connection caps; model allow-list; no prompt logging; failover to Google off by default |
| Installer | No `eval`; isolated Python (`-I`); backups before changes; refuses to write through symlinks |
| Supply chain | Standard library only; CI actions and container pinned by digest; Dependabot for actions |

Known limits: redaction covers well-known formats, not every secret; media can't be redacted; the gateway forwards whole conversations to Google unfiltered; a local user on the same machine can interrupt the gateway's availability (but can't use it without the token).

## Supported versions

Only the latest release receives security fixes.
