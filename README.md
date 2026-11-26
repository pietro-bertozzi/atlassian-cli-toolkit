# atlassian-cli-toolkit

`atl` is a personal, read-only command line tool for Atlassian Cloud, built on the official REST
APIs. It is meant for humans in a terminal and for coding agents calling shell commands.

**Status:** early development. Current scope: Jira Cloud only.

## Install

```bash
uv sync            # development environment
# or
pip install .      # plain pip works too
```

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
- Sprints, story points, issue history — planned

## Development

```bash
uv run pytest
uv run ruff format && uv run ruff check
```

Unit tests never touch the network, the real keyring or your real config directory.
