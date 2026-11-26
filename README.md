# atlassian-cli-toolkit

`atl` is a personal, read-only command line tool for Atlassian Cloud, built on the official REST
APIs. It is meant for humans in a terminal and for coding agents calling shell commands.

**Status:** early development. Current scope: Jira Cloud only.

## Install

Use `atl` in any project (needs [uv](https://docs.astral.sh/uv/)):

```bash
uv tool install git+https://github.com/pietro-bertozzi/atlassian-cli-toolkit@v0.1.0
atl setup claude-skill   # optional: teach Claude Code to use atl in all your projects
```

Upgrading and releases: [docs/releasing.md](docs/releasing.md). For development, clone the
repository and run `uv sync` (plain `pip install .` works too).

## Configure and first commands

```bash
atl auth login           # prompts for site, email and (hidden) API token
atl auth status          # shows the profile; never the token
atl -f json jira me      # checks that the credentials work
atl jira mine                # your open issues
atl jira issue get DEMO-123   # one issue, description as Markdown
```

Create an API token at <https://id.atlassian.com/manage-profile/security/api-tokens>.
The token is stored in your OS keyring, never in a config file. On headless machines set
`ATL_JIRA_API_TOKEN` instead. Details, scoped tokens, output formats and troubleshooting:
[docs/jira.md](docs/jira.md).

## Use from coding agents

`atl` is built to be called by coding agents such as Claude Code. See
[docs/agents.md](docs/agents.md) for setup, rules and recipes. `atl setup claude-skill`
installs a Claude Code skill (`~/.claude/skills/atl-jira`) so Claude uses `atl` in every
project.

## Discover commands

There is no `help` or `list` command: add `--help` at any level. The output is generated from
the code, so it is always current (useful for coding agents too).

```bash
atl --help              # groups: auth, jira
atl jira --help         # Jira commands
atl jira search --help  # arguments and options of one command
```

## Available / planned

- `atl auth login | status | logout` — available
- `atl jira me` — available
- `atl jira issue get` — available
- `atl jira search` (JQL), `atl jira mine` — available
- `atl jira issue comments`, `atl jira issue context` (all of an issue in one call, for
  agents) — available
- `atl jira projects`, `atl jira fields` (find custom field ids) — available
- `--field <id>` on issue/search commands (custom fields such as story points) — available
- Sprints, issue history — planned

## Development

```bash
uv run pytest
uv run ruff format && uv run ruff check
```

Unit tests never touch the network, the real keyring or your real config directory.

CI (GitHub Actions, `.github/workflows/ci.yml`) runs the format check, lint and unit tests on
Windows, macOS and Linux with Python 3.11 and 3.13, and checks that `pip install .` works on
each OS.
