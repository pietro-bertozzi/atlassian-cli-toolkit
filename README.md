# atlassian-cli-toolkit

`atl` is a personal, read-only command line tool for Atlassian Cloud, built on the official REST
APIs. It is meant for humans in a terminal and for coding agents calling shell commands.

**Status:** early development. Current scope: Jira Cloud only. Nothing is usable yet.

## Development setup

```bash
uv sync
uv run pytest
uv run ruff format --check && uv run ruff check
```

The package also installs with plain `pip install .`.

## Planned

- `atl auth login | status | logout` — *planned*
- `atl jira me` — *planned*

Credentials are never stored in config files: the API token goes to the OS keyring (or the
`ATL_JIRA_API_TOKEN` environment variable on headless machines).
