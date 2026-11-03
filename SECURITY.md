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

## Supported versions

Only the latest release receives security fixes.
