# Changelog

All notable changes to this project are documented in this file.
The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

### Added

- `docs/agents.md` and the Claude Code skill `.claude/skills/atl-jira`: how coding agents should
  use `atl` (setup, rules, recipes).
- `--field <id>` on `issue get`, `issue context`, `search` and `mine`: include any field
  (e.g. story points) by id; values are simplified and returned in `extra_fields`.
- `atl jira projects`: projects you can view (key, name, type, company/team-managed), with
  `--query` and `--limit`.
- `atl jira fields`: issue fields and their ids, with `--search` and `--custom`, to find
  custom fields such as story points.
- `atl jira issue comments <KEY>`: comments as Markdown, with `startAt` pagination,
  `--limit` and `--newest-first`.
- `atl jira issue context <KEY>`: issue fields, subtasks, links, description and comments in
  one call (for coding agents).
- `subtasks` and `links` in `issue get` output.
- README: how to discover commands with `--help`.
- `atl jira search "<JQL>"` and `atl jira mine`: list issues via `/rest/api/3/search/jql`
  with `nextPageToken` pagination and `--limit`.
- `status_category_key` in `issue get` output: the language-independent status category key
  (`status_category` is the translated name).
- `atl auth login --token-file PATH`: import the API token from a file (works in any terminal),
  store it in the OS keyring and delete the file. Empty or malformed tokens are now rejected.
- `atl jira issue get <KEY>`: show one issue's core fields, with the description converted
  from Atlassian Document Format (ADF) to Markdown. `-f markdown` prints a Markdown document.
- `atl auth login | status | logout`: profile and API token management (token stored in the OS
  keyring; `ATL_JIRA_API_TOKEN` overrides it for headless/CI use).
- `atl jira me`: show the user the API token authenticates as.
- Global options `--profile/-p`, `--format/-f` (`table`, `json`, `markdown`), `--verbose/-v`,
  `--version`. Exit codes: 3 configuration, 4 authentication, 5 not found, 6 API/network.
- `ATL_CONFIG_DIR` environment variable to relocate the config directory.
- Project skeleton: packaging, lint and test configuration.

### Fixed

- Tables written to a pipe or file are no longer cropped at 80 characters, and column headers
  (e.g. custom field ids) are never shortened.
