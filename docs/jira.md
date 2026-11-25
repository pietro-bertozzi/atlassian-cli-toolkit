# Jira (`atl auth`, `atl jira`)

Status legend: **available** = implemented and tested; **planned** = not implemented yet.

## 1. Concepts

- **Site**: your Jira Cloud address, e.g. `example.atlassian.net`.
- **Account / API token**: Atlassian lets you create a token for your own account at
  <https://id.atlassian.com/manage-profile/security/api-tokens>. The CLI authenticates with
  HTTP Basic auth: your account **email** + the **token**. The token can do what your account
  can do (classic) or only what its scopes allow (scoped).
- **Token modes** (chosen per profile):

  | Mode      | Token type             | Base URL                                       | Extra setting |
  | --------- | ---------------------- | ---------------------------------------------- | ------------- |
  | `classic` | unscoped               | `https://<site>`                               | none          |
  | `scoped`  | scoped (read-only advised) | `https://api.atlassian.com/ex/jira/<cloudId>` | `cloud_id`    |

  Source: <https://support.atlassian.com/atlassian-account/docs/manage-api-tokens-for-your-atlassian-account/>.
  Atlassian's pages do not say how to look up the `cloudId`; for now you supply it yourself.
  Only the client's base-URL logic depends on the mode.
- **Profile**: a named set of connection settings (site, email, mode, cloud id) so you can
  switch between sites/accounts. Profile selection: `--profile` > `ATL_PROFILE` >
  `default_profile` in the config file.
- Tokens expire (at most one year). An expired or revoked token shows up as HTTP 401, which the
  CLI reports as an authentication error (exit code 4).

## 2. Where secrets and settings live

| What                              | Where                                                              |
| --------------------------------- | ------------------------------------------------------------------ |
| Site, email, mode, cloud id       | `config.toml` in the OS user config dir (`$ATL_CONFIG_DIR` overrides the directory) |
| API token                         | OS keyring (service `atl-jira`, username = profile name)           |
| API token, headless/CI            | environment variable `ATL_JIRA_API_TOKEN`                          |

`ATL_JIRA_API_TOKEN`, when set, **overrides** the keyring for every profile. Tokens are never
written to the config file, never accepted as command-line arguments, and never printed or
logged. With no usable keyring (e.g. headless Linux), `atl auth login` fails with a message
pointing to the environment variable; there is no plaintext-file fallback.

## 3. Global options *(available)*

Placed **before** the command: `atl -f json jira me`.

| Option              | Meaning                                                       |
| ------------------- | ------------------------------------------------------------- |
| `-p, --profile`     | Profile to use                                                |
| `-f, --format`      | `table`, `json` or `markdown`. Default: `table` on a terminal, `json` otherwise |
| `-v, --verbose`     | Log requests (method, URL, status, retries) to stderr; never headers or tokens |
| `--version`         | Print version                                                 |

Data goes to stdout; messages, warnings and errors go to stderr. `--format json` prints only
JSON on stdout. Agents and scripts should pass `-f json` explicitly.

Exit codes: `0` ok · `1` unexpected · `2` usage · `3` configuration (incl. missing token) ·
`4` authentication/authorisation · `5` not found · `6` API/network.

## 4. Commands

### `atl auth login` *(available)*

Creates or updates a profile and stores its token in the keyring.

```bash
# Interactive: prompts for site, email and the token (hidden input)
atl auth login

# Non-interactive: token on stdin, everything else as options
printf '%s' "$TOKEN" | atl -p work auth login \
    --site example.atlassian.net --email alice@example.com --token-stdin

# Scoped token
printf '%s' "$TOKEN" | atl -p work auth login --site example.atlassian.net \
    --email alice@example.com --mode scoped --cloud-id <cloudId> --token-stdin
```

The profile name is `--profile`, else `ATL_PROFILE`, else `default`. The first profile created
becomes `default_profile`. `--site` may be a bare host or a URL (it is normalised). The token
is stored first; if that fails nothing is written to the config. Login does **not** call Jira;
use `atl jira me` to verify.

### `atl auth status` *(available)*

Shows the selected profile and where its token comes from (`keyring`, `environment` or `null`).
Never shows the token. Keys: `profile`, `site`, `email`, `mode`, `cloud_id`, `token_source`,
`config_path`.

### `atl auth logout` *(available)*

Deletes the selected profile and its keyring token. If `ATL_JIRA_API_TOKEN` is set it reminds
you that the variable is untouched.

### `atl jira me` *(available)*

Shows the user the token authenticates as. The quickest way to check that site, email and token
work.

- **Endpoint**: `GET /rest/api/3/myself`
  (<https://developer.atlassian.com/cloud/jira/platform/rest/v3/api-group-myself/>).
- **Permission**: permission to access Jira. **Scope** (scoped tokens): `read:jira-user`.
- **Jira web UI**: your profile (avatar menu → Profile).
- **JSON output** (stable keys): `account_id`, `display_name`, `email`, `active`, `time_zone`,
  `account_type`. `email`, `time_zone` and `account_type` can be `null`: Jira hides some fields
  according to the user's Atlassian Account privacy settings.

```bash
atl -f json jira me
```

### Planned

Issue lookup and JQL search (`/rest/api/3/search/jql`, token pagination), sprints/boards,
story points (custom field discovered per site), ADF → Markdown conversion. *(planned)*

## 5. HTTP behaviour *(available)*

- Timeout 30 s. Read-only GET requests are retried up to 3 times with exponential backoff and
  jitter: on 429 only when `Retry-After` is present and ≤ 60 s (otherwise fail fast), and on
  502/503/504 and network errors. See
  <https://developer.atlassian.com/cloud/jira/platform/rate-limiting/>.
- TLS verification is always on.
- 401 → "token may be expired or revoked" (exit 4); 403 → permission/scope problem (exit 4);
  404 → exit 5; other failures → exit 6. Jira's own error messages are appended (truncated).

## 6. Troubleshooting

| Symptom | Likely cause / fix |
| ------- | ------------------ |
| `No profile selected` (exit 3) | Run `atl auth login`, or pass `--profile` / set `ATL_PROFILE` |
| `No usable OS keyring` (exit 3) | Headless machine: export `ATL_JIRA_API_TOKEN` instead |
| HTTP 401 (exit 4) | Token expired/revoked, or email does not belong to the token; create a new token and log in again |
| HTTP 401 with a scoped token | Wrong `cloud_id`, or the token lacks a scope (`read:jira-user` for `me`) |
| HTTP 403 (exit 4) | The account/token lacks permission for that resource |
| Unexpected account is used | `ATL_JIRA_API_TOKEN` overrides the keyring; check `atl auth status` → `token_source` |
