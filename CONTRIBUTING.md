# Contributing

Thanks for helping. Bug reports, fixes and new commands are all welcome.

## Before you start

- For anything larger than a small fix, open an issue first so we can agree on the approach.
- Security problems: do not open a public issue. See [SECURITY.md](./SECURITY.md).

## Setup

No dependencies to install. You need Python 3.9 or newer and git.

```bash
git clone https://github.com/vmishra/gemini-sidecar.git && cd gemini-sidecar
./verify.sh          # offline checks and unit tests; no credentials needed
```

To try your changes in Claude Code without installing from the marketplace:

```bash
claude --plugin-dir ./plugins/gemini
```

## Ground rules

- **Standard library only.** The MCP server and gateway must run on a stock Python 3.9 with nothing to `pip install`.
- **Tests stay offline.** Mock `urllib.request.urlopen`; never call a real API from `tests/`. `./verify.sh` must pass on Python 3.9 and 3.13.
- **Security changes need a regression test.** Anything touching path handling, secret filtering, staging or the gateway's auth comes with a test that fails without the fix.
- **Claims need evidence.** Numbers in the README come from measured runs or official pricing pages, with the date. Don't add benchmark or pricing claims without a source.

## Adding a command

A command is a skill in `plugins/gemini/skills/<name>/SKILL.md`:

1. Set `disable-model-invocation: true`, so code is only sent to Gemini when the user runs the command.
2. List only the tools the command needs in `allowed-tools`. Use exact commands, not wildcards that could run arbitrary programs.
3. If the command needs new server behaviour, add a tool in `gemini4_mcp_server.py` with tests in `tests/test_mcp_server.py`.
4. Add the command to the README table, with an example.

`./verify.sh` checks that every `mcp__plugin_gemini_gemini4__*` reference in a skill points to a tool the server exposes.

## Pull requests

Keep PRs focused, describe what you tested, and update the README and `CHANGELOG.md` when behaviour changes.
