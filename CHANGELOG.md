# Changelog

All notable changes to this project are documented in this file.
The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

### Added

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
