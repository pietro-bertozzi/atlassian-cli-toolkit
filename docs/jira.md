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

#### Token from a file (works in any terminal)

Hidden prompts are unreliable on some terminals (Git Bash, the VS Code terminal, some
PowerShell setups): pasting may do nothing, and because nothing is shown you cannot tell.
Pasting into an editor always works, so the toolkit can import the token from a file:

1. In the repository, create `.secrets/jira-token.txt`, paste the token into it (VS Code,
   Notepad...) and save. Only the token, nothing else. The `.secrets/` folder is listed in
   `.gitignore`, so git never commits it, and `.claude/settings.json` denies Claude Code
   reading it. Any other path also works.
2. Run (the same command works in Git Bash, PowerShell, macOS and Linux):

   ```bash
   uv run atl auth login --site example.atlassian.net --email alice@example.com --token-file .secrets/jira-token.txt
   ```

The token is stored in the keyring and **the file is deleted**. If storing fails (e.g. no
keyring) the file is kept and nothing is saved. A leading BOM and trailing newline (as some
Windows editors write) are ignored; a token containing spaces or line breaks is rejected.

Close the editor tab without saving again, so the editor does not recreate the file. Atlassian
shows a token only once: if you no longer have it, revoke it and create a new one.

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

### `atl jira issue get <KEY>` *(available)*

Shows one issue: its core fields and its description converted to Markdown. Use it to read a
ticket from the terminal or to hand a ticket to a coding agent as clean text.

**Concepts**

- **Issue**: a unit of work in Jira (a bug, a story, a task...). It belongs to one **project**.
- **Key vs id**: the key (`DEMO-123`) is the project key plus a number; it is what people use
  and what appears in URLs. The id (`10001`) is Jira's internal number. Both work as argument.
  If an issue was moved to another project its key changes; Jira still finds it by the old key
  and returns the **current** key, so `key` in the output can differ from what you typed.
- **Issue type**: Bug, Story, Task, Epic, Sub-task... Each site/project defines its own set.
- **Status vs status category**: the status is the workflow step and its name is chosen by
  each team (`In Review`, `QA`, `Da completare`...). Every status belongs to a **category**
  (in English: To Do, In Progress, Done). The category *name* is translated into the user's
  language (`status_category`, e.g. `Da completare` for an Italian user); the category *key*
  is not (`status_category_key`, e.g. `new`). Scripts that must work across projects and
  languages should use `status_category_key`. The API spec does not list the possible keys;
  `new` was observed for a To Do-category status.
- **Parent**: the epic of a story, or the story/task of a sub-task.
- **Description and ADF**: rich text in Jira REST API v3 is returned as
  [Atlassian Document Format](https://developer.atlassian.com/cloud/jira/platform/apis/document/structure/),
  a JSON tree of nodes (paragraphs, lists, tables, mentions...). The CLI converts it to
  GitHub-flavoured Markdown.

**Details**

- **Jira web UI**: open `https://<site>/browse/DEMO-123` (the `url` key in the output).
- **Endpoint**: `GET /rest/api/3/issue/{issueIdOrKey}` with an explicit `fields` list
  (<https://developer.atlassian.com/cloud/jira/platform/rest/v3/api-group-issues/#api-rest-api-3-issue-issueidorkey-get>).
  Only the fields below are requested; custom fields are not.
- **Permissions**: *Browse projects* on the issue's project, and the issue security level if
  the project uses issue security. **Scope** (scoped tokens): `read:jira-work`.
- **JSON output** (stable keys): `key`, `id`, `url`, `summary`, `issue_type`, `status`,
  `status_category`, `status_category_key`, `priority`, `project_key`, `parent_key`, `assignee`, `reporter`
  (display names), `labels` (list), `resolution`, `created`, `updated` (ISO 8601 as returned
  by Jira), `due_date` (`YYYY-MM-DD`), `description` (Markdown). Optional values are `null`
  when unset.
- **Markdown output** (`-f markdown`) is a document: `# KEY: summary`, a metadata list, then a
  `## Description` section.

```bash
atl -f json jira issue get DEMO-123
atl -f markdown jira issue get DEMO-123 > DEMO-123.md
```

**ADF conversion**

| ADF | Markdown |
| --- | -------- |
| paragraph, heading (levels 1–6), bullet/ordered list (start number kept), blockquote, rule | the same construct |
| code block | fenced block with language |
| bold, italic, strikethrough, inline code, link | `**`, `*`, `~~`, backticks, `[text](url)` |
| panel (info, note, warning, success, error) | blockquote starting with `**Info:**` etc. |
| table | GFM table; cells flattened to one line; empty header row if the table has none |
| expand | bold title followed by the content |
| mention, emoji, status lozenge, date, smart link | `@Name`, the emoji, `[STATUS]`, `YYYY-MM-DD`, `<url>` |
| images and attachments | `[attachment]` placeholder |
| underline, text colour, sub/superscript | dropped (text kept) |
| any other node (e.g. task lists) | its text is kept, its structure is lost |

**Limitations**

- Comments, attachments, links between issues, worklogs and custom fields (story points,
  sprint...) are not shown yet.
- Attachments are not downloaded; table cell merges (colspan/rowspan) are ignored.
- Markdown characters typed as plain text in Jira (e.g. `*word*`) are not escaped, so they
  render as Markdown formatting.
- ADF `date` nodes: the docs do not state the timestamp unit. Values above 10^11 are read as
  milliseconds, others as seconds; dates are shown in UTC.
- HTTP 404 means *either* the issue does not exist *or* you are not allowed to see it; Jira
  does not say which.

### `atl jira search "<JQL>"` and `atl jira mine` *(available)*

Lists issues matching a query. `mine` is a shortcut for your open work.

**Concepts**

- **JQL** (Jira Query Language) is the search language behind Jira's issue search
  (<https://confluence.atlassian.com/x/egORLQ>, the link used by the REST API reference).
  Example: `project = DEMO AND statusCategory != Done ORDER BY updated DESC`.
- `currentUser()` is the user the token belongs to.
- The query must be **bounded**: it needs at least one restriction (`project = X`,
  `assignee = currentUser()`...). A bare `ORDER BY key` is rejected.

**Details**

- **Jira web UI**: the issue search page in JQL (advanced) mode; paste the same query there
  to compare results.
- **Endpoint**: `GET /rest/api/3/search/jql`
  (<https://developer.atlassian.com/cloud/jira/platform/rest/v3/api-group-issue-search/#api-rest-api-3-search-jql-get>).
  Pages are fetched with `nextPageToken` until the last page or `--limit` is reached (100
  issues per request). The old `/rest/api/3/search` endpoint is not used.
- `mine` runs `assignee = currentUser() AND statusCategory != Done ORDER BY updated DESC`.
- **Permissions**: only issues you can browse are returned. **Scope**: `read:jira-work`.
- **Options**: `--limit/-n` (default 50, max 1000). When more issues match, a note is printed
  on stderr; stdout stays valid JSON.
- **JSON output**: a list of objects with the stable keys `key`, `summary`, `status`,
  `status_category`, `status_category_key`, `issue_type`, `priority`, `assignee`, `updated`,
  `url`. The table and Markdown formats show `key`, `status`, `priority`, `issue_type`,
  `summary`. No description (use `issue get` for that).

```bash
atl jira mine
atl -f json jira search "project = DEMO AND updated >= -7d ORDER BY updated DESC" --limit 200
```

**Limitations**: search results may lag a few seconds behind recent edits (Jira's search
index); the `reconcileIssues` option for read-after-write consistency is not exposed.

### Planned

Issue comments, sprints/boards, story points (custom field discovered per site). *(planned)*

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
| Cannot paste the token into the hidden prompt | Use `--token-file` (see "Token from a file" under `atl auth login`) |
| HTTP 401 (exit 4) | Token expired/revoked, or email does not belong to the token; create a new token and log in again |
| HTTP 401 with a scoped token | Wrong `cloud_id`, or the token lacks a scope (`read:jira-user` for `me`) |
| HTTP 403 (exit 4) | The account/token lacks permission for that resource |
| `search` gives HTTP 400 (exit 6) | Invalid or unbounded JQL; Jira's message is shown. Add a restriction such as `project = X` |
| `issue get` gives HTTP 404 (exit 5) | Wrong key, or you lack *Browse projects* / issue security permission for it. Check by opening `https://<site>/browse/<KEY>` in the browser with the same account |
| `issue get` fails with a scoped token | The token needs the `read:jira-work` scope |
| Unexpected account is used | `ATL_JIRA_API_TOKEN` overrides the keyring; check `atl auth status` → `token_source` |
