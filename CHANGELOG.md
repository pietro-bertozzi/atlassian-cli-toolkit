# Changelog

All notable changes to this project are documented in this file.
The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

### Added

- Write commands, with a preview, `--dry-run`, and a y/N prompt on a terminal or `--yes`
  otherwise:
  - `atl jira issue comment KEY --body/--body-file`: add a comment written in Markdown
    (converted to Atlassian Document Format);
  - `atl jira issue transition KEY --to NAME`: move an issue to another status;
  - `atl jira issue assign KEY --to me|NAME | --account-id ID | --unassign`.
- `atl jira issue get` shows the possible status changes (`transitions`) in the same request,
  and `--comments` accepts `--newest-first`.
- `atl auth login --mode scoped` finds the site's Cloud ID automatically (documented
  `/_edge/tenant_info` endpoint); `--cloud-id` is now optional. Docs list the scopes each
  command needs and recommend a read-only scoped token for everyday and agent use.
- `atl auth login` safety nets: it says when it is about to replace an existing profile;
  rejects tokens containing characters API tokens do not have (e.g. a chat message's `12:34`
  copied with the token); and with `--mode scoped` warns when the token is actually a classic
  one, which scopes do not limit.
- A write refused because the token lacks a scope now says which scope is missing (Jira's
  "scope does not match"), not "token may be expired or revoked".

### Changed

- **Breaking:** `atl jira me` is replaced by `atl auth status --check` (adds `check`,
  `account_id`, `display_name` to the status record).
- **Breaking:** `atl jira issue context KEY` and `atl jira issue comments KEY` are replaced by
  `atl jira issue get KEY --comments` (`-n` limits the comments, `--newest-first` reverses
  them).
- HTTP client: POST requests are never retried after a network error or 5xx (no duplicate
  comments); PUT is retried like GET.
- The `atl-jira` Claude Code skill pre-approves only read commands, so Claude Code asks
  before every write, and tells agents to write only with the user's approval. Re-run
  `atl setup claude-skill --force` after upgrading.

## [0.1.0] - 2026-11-26

### Added

- `atl setup claude-skill`: install the packaged `atl-jira` Claude Code skill in
  `~/.claude/skills` so Claude Code uses `atl` in every project.
- Release workflow: pushing a `vX.Y.Z` tag runs the tests, builds the package and publishes a
  GitHub release; see `docs/releasing.md`. Install anywhere with
  `uv tool install git+https://github.com/pietro-bertozzi/atlassian-cli-toolkit@vX.Y.Z`.
- CI: format check, lint and unit tests on Windows, macOS and Linux (Python 3.11 and 3.13),
  plus a plain `pip install .` check on each OS.
- `docs/agents.md` and the `atl-jira` Claude Code skill: how coding agents should
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
