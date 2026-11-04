---
name: deps
description: Check your dependencies against live Google Search results - latest versions, known vulnerabilities in the versions you declare, and breaking changes - with source links.
argument-hint: "[manifest paths] [--focus <area>]"
disable-model-invocation: true
allowed-tools: mcp__plugin_gemini_gemini4__gemini4_check_dependencies
---

# Dependency check with Gemini and Google Search

Request: $ARGUMENTS

1. Manifests: use any paths in the request (for example `requirements.txt`, `package.json`). Otherwise omit `paths`; the tool finds the manifests itself.
2. If the request contains `--focus <area>` (for example "security only" or "plan a Django 5 upgrade"), pass it as `focus`.
3. Call `gemini4_check_dependencies`.
4. Present the table and the sources. Lead with anything that has a known vulnerability. Gemini's answer is grounded in search results, so point the user to the listed sources before acting on a specific CVE.
5. Offer to bump the safe upgrades and run the tests. Change nothing until the user agrees, and do major-version upgrades one at a time.
