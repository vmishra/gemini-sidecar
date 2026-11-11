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
| File access | Workspace confinement (no absolute paths outside, `..`, or escaping symlinks); `/`, home, parents of home, top-level and shared temp directories refused as roots; a narrowed `workspace_root` may not sit inside `.git` or a credential folder; gitignored files skipped even when named; secret file names and credential folders (`.ssh`, `.aws`, `.kube`, `.docker`, `.git`, bare repos) never read |
| Data sent | Common token formats, private keys, JWTs, URL passwords and secret-named literals redacted from file contents, diffs, logs and typed prompts; media (images, video, PDF) is sent as-is |
| Untrusted repositories | git runs with hooks, fsmonitor, external diff, textconv and pager disabled; every repository-defined filter driver is neutralised through `GIT_CONFIG_KEY_n`/`GIT_CONFIG_VALUE_n`, so driver names containing `=` cannot slip past; a `.git` file is trusted only when its git directory belongs to that working tree (linked worktrees and submodules that point back); embedded bare repositories refused; diffs forced to text |
| Network | Spec URLs are fetched by the server, not by the model: `https` only, public addresses only (no loopback, private or link-local ranges, so no cloud metadata), every redirect hop re-checked, size-capped. No fetch tool is ever enabled in a call that carries workspace code |
| Writes | Only under `.gemini4-staging/<run>/`; `.git` paths, symlinked staging, secret names and `..` refused; CI, hook and agent-config targets flagged |
| Gateway | Loopback only; 32+ character token in a `0600` file (no symlinks); `Origin`/`Host` checks against browsers and DNS rebinding; size and connection caps; model allow-list; no prompt logging; failover to Google off by default |
| Installer | No `eval`; isolated Python (`-I`); backups before changes; refuses to write through symlinks |
| Supply chain | Standard library only; CI actions and container pinned by digest; Dependabot for actions |

Known limits: redaction covers well-known formats, not every secret; media can't be redacted; the gateway forwards whole conversations to Google unfiltered; a local user on the same machine can interrupt the gateway's availability (but can't use it without the token).

## Supported versions

Only the latest release receives security fixes.
