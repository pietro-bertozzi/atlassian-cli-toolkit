# Jira (`atl auth`, `atl jira`)

Status legend: **available** = implemented and tested; **planned** = not implemented yet.

## 1. Concepts

- **Site**: your Jira Cloud address, e.g. `example.atlassian.net`.
- **Account / API token**: Atlassian lets you create a token for your own account at
  <https://id.atlassian.com/manage-profile/security/api-tokens>. The CLI authenticates with
  HTTP Basic auth: your account **email** + the **token**. The token can do what your account
  can do (classic) or only what its scopes allow (scoped).
- **Token modes** (chosen per profile):

  | Mode      | Token type | Can do | Base URL | Extra setting |
  | --------- | ---------- | ------ | -------- | ------------- |
  | `classic` | "API token" (without scopes) | everything your account can do | `https://<site>` | none |
  | `scoped`  | "API token with scopes" (Atlassian's recommendation) | only the scopes you pick | `https://api.atlassian.com/ex/jira/<cloudId>` | `cloud_id` (found automatically) |

  Sources: <https://support.atlassian.com/atlassian-account/docs/manage-api-tokens-for-your-atlassian-account/>,
  <https://support.atlassian.com/atlassian-cloud/kb/401-unauthorized-error-when-service-account-accesses-jira-or-confluence-api/>.
  Only the client's base-URL logic depends on the mode.
- **Cloud ID**: the id of your site, needed by scoped tokens. `atl auth login --mode scoped`
  reads it from `https://<site>/_edge/tenant_info` (no credentials sent), the method documented
  in <https://support.atlassian.com/jira/kb/retrieve-my-atlassian-sites-cloud-id/>; that page
  also shows how to find it by hand (admin.atlassian.com) if you need `--cloud-id`.
- **Recommended setup**: a **scoped token with read scopes only** for everyday and agent use:
  Jira itself then refuses any write, whatever the CLI does. When you want the write commands,
  use a second profile with a token that also has the write scope (or your classic token),
  e.g. `atl -p write jira issue comment ...`.
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

Placed **before** the command: `atl -f json jira mine`. With `-f table` and output that is
not a terminal (a pipe or a file), tables are 160 characters wide and column headers are never
shortened.

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

# Scoped token (Cloud ID found automatically; add --cloud-id <id> to skip the lookup)
atl -p work auth login --site example.atlassian.net --email alice@example.com \
    --mode scoped --token-file .secrets/jira-token.txt
```

#### Creating a scoped token

1. Open <https://id.atlassian.com/manage-profile/security/api-tokens> → **Create API token
   with scopes**; give it a name and an expiry (1–365 days).
2. App: **Jira**. Scopes: tick the ones in the table below for the commands you want. For a
   read-only token: `read:jira-work` and `read:jira-user` (or, if the page shows granular
   scopes, the granular ones listed for the read commands).
3. Copy the token, then log in with `--mode scoped` as above and verify with
   `atl -p work auth status --check`.

#### Scopes needed per command

From the official REST API specification (classic scope, and the granular scopes Atlassian
lists for the same endpoint):

| Command | Classic scope | Granular scopes |
| ------- | ------------- | --------------- |
| `auth status --check` | `read:jira-user` | `read:user:jira`, `read:application-role:jira`, `read:group:jira`, `read:avatar:jira` |
| `search`, `mine` | `read:jira-work` | `read:issue-details:jira`, `read:audit-log:jira`, `read:avatar:jira`, `read:field-configuration:jira`, `read:issue-meta:jira` |
| `issue get` | `read:jira-work` | `read:issue:jira`, `read:issue-meta:jira`, `read:issue-security-level:jira`, `read:issue.vote:jira`, `read:issue.changelog:jira`, `read:avatar:jira`, `read:status:jira`, `read:user:jira`, `read:field-configuration:jira` |
| `issue get --comments` | `read:jira-work` | `read:comment:jira`, `read:comment.property:jira`, `read:group:jira`, `read:project:jira`, `read:project-role:jira`, `read:user:jira`, `read:avatar:jira` |
| `issue get` (possible status changes), `issue transition` (lookup) | `read:jira-work` | `read:issue.transition:jira`, `read:status:jira`, `read:field-configuration:jira` |
| `projects` | `read:jira-work` | `read:project:jira`, `read:issue-type:jira`, `read:project.property:jira`, `read:user:jira`, `read:application-role:jira`, `read:avatar:jira`, `read:group:jira`, `read:issue-type-hierarchy:jira`, `read:project-category:jira`, `read:project-version:jira`, `read:project.component:jira` |
| `fields` | `read:jira-work` | `read:field:jira`, `read:avatar:jira`, `read:project-category:jira`, `read:project:jira`, `read:field-configuration:jira` |
| `issue assign --to NAME` (user search) | `read:jira-user` | `read:user:jira`, `read:issue:jira`, `read:project:jira`, `read:application-role:jira`, `read:avatar:jira`, `read:group:jira` |
| `issue comment` | `write:jira-work` | `write:comment:jira` (+ the read scopes of `issue get --comments`) |
| `issue transition` | `write:jira-work` | `write:issue:jira`, `write:issue.property:jira` |
| `issue assign` | `write:jira-work` | `write:issue:jira` |

A missing scope shows up as HTTP 401 or 403 (exit 4).

The profile name is `--profile`, else `ATL_PROFILE`, else `default`. The first profile created
becomes `default_profile`. `--site` may be a bare host or a URL (it is normalised). The token
is stored first; if that fails nothing is written to the config. Login does **not** call Jira;
use `atl auth status --check` to verify.

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
`config_path`. It works offline: it does not contact Jira.

`--check` also asks Jira who the token belongs to — the quickest way to test that site, email
and token work. It adds `check` (`"ok"`), `account_id` and `display_name`; a bad or expired
token gives exit 4, a network problem exit 6.

- **Endpoint**: `GET /rest/api/3/myself`
  (<https://developer.atlassian.com/cloud/jira/platform/rest/v3/api-group-myself/>).
- **Scope** (scoped tokens): `read:jira-user`.

```bash
atl -f json auth status --check
```

### `atl auth logout` *(available)*

Deletes the selected profile and its keyring token. If `ATL_JIRA_API_TOKEN` is set it reminds
you that the variable is untouched.

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
  Only the fields below are requested; other fields (e.g. custom fields such as story
  points) only when asked for with `--field` (see "Extra fields" below).
- **Permissions**: *Browse projects* on the issue's project, and the issue security level if
  the project uses issue security. **Scope** (scoped tokens): `read:jira-work`.
- **JSON output** (stable keys): `key`, `id`, `url`, `summary`, `issue_type`, `status`,
  `status_category`, `status_category_key`, `priority`, `project_key`, `parent_key`, `assignee`, `reporter`
  (display names), `labels` (list), `resolution`, `created`, `updated` (ISO 8601 as returned
  by Jira), `due_date` (`YYYY-MM-DD`), `subtasks`, `links`, `description` (Markdown),
  `extra_fields` (object, `{}` unless `--field` is used). Optional values are `null` when
  unset; `subtasks`, `links` and `transitions` are empty lists when there are none.
  - `subtasks`: list of `{key, summary, status, status_category_key, issue_type}`.
  - `links`: the same keys plus `relation`, Jira's wording for the link seen from this issue,
    e.g. `blocks` (this issue blocks `key`) or `is blocked by` (`key` blocks this issue).
  - `transitions`: the status changes you can make now (see `issue transition`), list of
    `{id, name, to_status, to_status_category_key, has_screen}`. Returned in the same request
    (`expand=transitions`); empty if you lack *Transition issues*.
- **Markdown output** (`-f markdown`) is a document: `# KEY: summary`, a metadata list, then
  `## Description`, `## Subtasks`, `## Links` and `## Possible status changes` sections (each
  only when not empty). In the table format each subtask/link is one line
  (`KEY [status] summary`) and each transition `Name -> Status`.

**With `--comments`**: everything about the issue in one call (2+ requests), the recommended
input for an agent. Comments are the discussion on an issue; decisions and clarifications
often live there rather than in the description.

- Oldest first; `--newest-first` reverses; `-n/--limit` (default 100, max 1000) caps them,
  with a note on stderr when more exist.
- JSON gets an extra `comments` key: list of `{id, author, created, updated, visibility,
  body}` (`body` in Markdown, `author` a display name). A comment can be **restricted** to a
  group or project role: it is returned only if you belong to it, and `visibility` names the
  group/role (`null` when unrestricted).
- Markdown gets a `## Comments` section, one `### author · created` heading per comment (plus
  `edited ...` and `visible to ...` when relevant); the table format prints a comments table
  after the issue.
- Endpoint: `GET /rest/api/3/issue/{issueIdOrKey}/comment`
  (<https://developer.atlassian.com/cloud/jira/platform/rest/v3/api-group-issue-comments/#api-rest-api-3-issue-issueidorkey-comment-get>),
  offset pagination (`startAt`, up to 100 per request).
- Jira web UI: the *Activity* section of an issue, *Comments* tab.

```bash
atl -f json jira issue get DEMO-123
atl -f markdown jira issue get DEMO-123 --comments > DEMO-123.md
atl -f json jira issue get DEMO-123 --comments --newest-first -n 5
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

- Comments are included only with `--comments`.
  Attachments, worklogs, history and custom fields (story points, sprint...) are not shown yet.
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
- **Options**: `--limit/-n` (default 50, max 1000), `--field` (see "Extra fields"). When
  more issues match, a note is printed on stderr; stdout stays valid JSON.
- **JSON output**: a list of objects with the stable keys `key`, `summary`, `status`,
  `status_category`, `status_category_key`, `issue_type`, `priority`, `assignee`, `updated`,
  `url`, `extra_fields`. The table and Markdown formats show `key`, `status`, `priority`,
  `issue_type`, `summary`, plus one column per `--field`. No description (use `issue get`).

```bash
atl jira mine
atl -f json jira search "project = DEMO AND updated >= -7d ORDER BY updated DESC" --limit 200
```

**Limitations**: search results may lag a few seconds behind recent edits (Jira's search
index); the `reconcileIssues` option for read-after-write consistency is not exposed.

### `atl jira projects` *(available)*

Lists the projects you can view, so you (or an agent) know which project keys to use in JQL.

- **Concepts**: a **project** groups issues and has a key (`DEMO`) used as issue-key prefix.
  `project_type` is `software`, `service_desk`, `business` or `product_discovery`. `style`
  tells who configures the project: `classic` = **company-managed** (Jira admins, shared
  workflows and fields) or `next-gen` = **team-managed** (the team itself; its fields belong
  to that project). The two kinds can use different fields for the same thing, e.g. story
  points.
- **Jira web UI**: *Projects* → *View all projects*.
- **Endpoint**: `GET /rest/api/3/project/search`
  (<https://developer.atlassian.com/cloud/jira/platform/rest/v3/api-group-projects/#api-rest-api-3-project-search-get>),
  ordered by key, offset pagination (`startAt`, 100 per request) until `isLast`. Jira answers
  404 when nothing matches `--query`; the CLI shows that as an empty list (exit 0).
- **Permissions**: *Browse projects* (or project/Jira admin) on each project returned.
  **Scope**: `read:jira-work`.
- **Options**: `--query/-q` (key or name contains, case insensitive), `--limit/-n` (default
  200, max 1000).
- **JSON output**: list of `{key, id, name, project_type, style, url}`.

```bash
atl jira projects
atl -f json jira projects -q demo
```

### `atl jira fields` *(available)*

Lists issue fields with their ids. Use it to find custom fields such as story points, whose
id (`customfield_NNNNN`) differs from site to site.

- **Concepts**: every issue value lives in a **field**. System fields have readable ids
  (`summary`, `labels`); **custom fields** are added per site and have ids like
  `customfield_10016`. The REST API uses the `id`; JQL uses one of the `clause_names`
  (e.g. `cf[10016]` or the field name).
- **Jira web UI**: custom fields are managed by Jira admins in the Jira administration
  settings, or by the team in the project settings of a team-managed project.
- **Endpoint**: `GET /rest/api/3/field`
  (<https://developer.atlassian.com/cloud/jira/platform/rest/v3/api-group-issue-fields/#api-rest-api-3-field-get>),
  one request, no paging. Filtering is done by the CLI.
- **Permissions**: none beyond access to Jira. **Scope**: `read:jira-work`.
- **Options**: `--search/-s TEXT` (name, id or JQL name contains, case insensitive),
  `--custom` (custom fields only).
- **JSON output**: list of `{id, name, custom, type, items, custom_type, clause_names,
  scope_project_id}`, sorted by name. `type`/`items` are the value type (e.g. `number`,
  `array` of `string`); `custom_type` identifies the custom field type;
  `scope_project_id` is set for a field that exists only in one (team-managed) project.

```bash
atl jira fields --search "story point"
atl -f json jira fields --custom
```

**Limitation**: on a site tested so far, a team-managed project's fields did not report a
`scope`; do not rely on `scope_project_id` alone to tell which project uses a field.

### Extra fields: `--field` *(available)*

`issue get`, `search` and `mine` accept `--field <id>` to include any other
field, typically a custom field such as story points. Repeat the option or separate ids with
commas. Unknown ids are not an error: Jira just omits them and the value is `null`.

1. Find the id once per site: `atl jira fields --search "story point"` (for example
   `customfield_10016`; the number differs per site, and company- and team-managed projects
   may use different fields).
2. Use it:

```bash
atl jira mine --field customfield_10016
atl -f json jira issue get DEMO-123 --comments --field customfield_10016,customfield_10020
```

- **JSON**: values go in `extra_fields`, keyed by id: `{"customfield_10016": 5.0}`.
- **Table / Markdown**: each requested field is shown as its own key or column.
- **Values are simplified**: numbers, strings and dates are kept; rich text (ADF) becomes
  Markdown; an object becomes its label (an option's value, a user's display name, or a
  `name`/`key`, e.g. a sprint becomes its name; cascading options become `parent / child`);
  lists are simplified item by item; other objects are kept without link/avatar noise. The
  rest of the raw object (e.g. a sprint's state and dates) is not shown.
- Field ids must look like `customfield_10016` or `fixVersions`; anything else is a usage
  error (exit 2).

### Write commands *(available)*

`atl` can add a comment, move an issue to another status and assign it. Creating or editing
issues is not supported.

**Safety model** (the same for every write command):

1. **Preview.** The exact change is printed on stderr before anything is sent.
2. **`--dry-run`** prints the preview and the request, sends nothing.
3. **Confirmation.** On a terminal you are asked `Proceed? [y/N]`. When not interactive
   (scripts, agents) the command refuses (exit 2) unless `--yes` is given.
4. **No duplicate writes.** A comment or transition (POST) is never retried after a network
   error or a 5xx answer, because Jira may already have applied it: the error tells you to
   check in Jira. Only "429 Too Many Requests" with `Retry-After` is retried (not processed).
5. **Token scopes.** A read-only scoped token cannot write at all: Jira refuses (exit 4).
   For writes use a token with `write:jira-work` (e.g. in a separate profile). Jira project
   permissions apply as in the web UI.
6. **Coding agents.** The `atl-jira` Claude Code skill pre-approves read commands only, so
   Claude Code asks you before every write.

Output: stdout gets a JSON-friendly record with `"dry_run": true|false` and the result;
messages go to stderr.

#### `atl jira issue comment KEY (--body TEXT | --body-file PATH)`

Adds a comment. The text is Markdown, converted to Atlassian Document Format: paragraphs (a
single line break is kept), headings, bullet/ordered lists (one nesting level), fenced code
blocks, bold, italic, strikethrough, inline code and `[text](https://...)` links. Anything else
is sent as plain text. `--body-file -` reads stdin.

- **Endpoint**: `POST /rest/api/3/issue/{issueIdOrKey}/comment`
  (<https://developer.atlassian.com/cloud/jira/platform/rest/v3/api-group-issue-comments/#api-rest-api-3-issue-issueidorkey-comment-post>).
- **Permissions**: *Browse projects* and *Add comments*.
- **Output**: `{key, dry_run, comment_id, created}` (dry run: `{key, dry_run, request}`).

```bash
atl jira issue comment DEMO-123 --body "Fixed in **v2.3**, see [PR](https://example.com/pr/1)"
atl -f json jira issue comment DEMO-123 --body-file note.md --yes
```

#### `atl jira issue transition KEY --to NAME`

- **Concepts**: a **status** is where an issue is (To Do, In Review...). A **transition** is
  a named move between statuses defined by the project's **workflow** ("Start progress",
  "Send to review"). Which transitions exist depends on the current status, the workflow and
  your permissions: `atl jira issue get KEY` shows them ("Possible status changes"). Some
  transitions open a **screen** (a form) in the
  web UI; `atl` cannot fill it, so if the screen has required fields Jira rejects the move
  (HTTP 400, exit 6) and you have to do it in the browser (`has_screen` warns you).
- `--to` matches a transition name or, failing that, a target status name (case
  insensitive). No match or several matches → exit 2 with the list of options.
- **Endpoints**: `GET` and `POST /rest/api/3/issue/{issueIdOrKey}/transitions`
  (<https://developer.atlassian.com/cloud/jira/platform/rest/v3/api-group-issues/#api-rest-api-3-issue-issueidorkey-transitions-get>).
- **Permissions**: *Browse projects* and *Transition issues*.
- **Output**: `{key, transition, transition_id, to_status, dry_run}`.

```bash
atl jira issue get DEMO-123              # see "Possible status changes"
atl jira issue transition DEMO-123 --to "In Review"
```

#### `atl jira issue assign KEY (--to me|NAME | --account-id ID | --unassign)`

- `--to me` assigns to the token's user. `--to NAME` searches the users who can be assigned
  to this issue (display name or email, prefix match): an exact name/email match wins,
  otherwise exactly one result is required; several → exit 2 listing them (inactive users are
  ignored). `--account-id` skips the search. `--unassign` removes the assignee.
- **Endpoints**: `PUT /rest/api/3/issue/{issueIdOrKey}/assignee` with `{"accountId": ...}`
  (`null` = unassigned)
  (<https://developer.atlassian.com/cloud/jira/platform/rest/v3/api-group-issues/#api-rest-api-3-issue-issueidorkey-assignee-put>);
  user search `GET /rest/api/3/user/assignable/search`
  (<https://developer.atlassian.com/cloud/jira/platform/rest/v3/api-group-user-search/#api-rest-api-3-user-assignable-search-get>).
- **Permissions**: *Browse projects* and *Assign issues*. **Scope** for the search:
  `read:jira-user`.
- **Output**: `{key, assignee, account_id, dry_run}`.

```bash
atl jira issue assign DEMO-123 --to me
atl jira issue assign DEMO-123 --unassign --dry-run
```

### Not planned for now

Creating or editing issues, sprints/boards, issue history, attachments.

## 5. HTTP behaviour *(available)*

- Timeout 30 s. GET and PUT requests are retried up to 3 times with exponential backoff and
  jitter: on 429 only when `Retry-After` is present and ≤ 60 s (otherwise fail fast), and on
  502/503/504 and network errors. POST requests (comment, transition) are retried only on such
  a 429, never after a network error or 5xx (they may already be applied). See
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
| HTTP 401 with a scoped token | Wrong `cloud_id`, the token lacks a scope (see "Scopes needed per command"), or it is a classic token used with `--mode scoped` |
| `Could not find the Cloud ID` at login | Network/proxy blocks the lookup: pass `--cloud-id` (see the Cloud ID link in section 1) |
| HTTP 403 (exit 4) | The account/token lacks permission for that resource |
| `Not confirmed: nothing was sent` (exit 2) | Not on a terminal: add `--yes` after checking the preview |
| `transition` fails with HTTP 400 (exit 6) | The transition's screen has required fields: do it in the browser |
| `may or may not have been applied` (exit 6) | Network error or 5xx during a comment/transition: check the issue in Jira before retrying |
| `search` gives HTTP 400 (exit 6) | Invalid or unbounded JQL; Jira's message is shown. Add a restriction such as `project = X` |
| `issue get` gives HTTP 404 (exit 5) | Wrong key, or you lack *Browse projects* / issue security permission for it. Check by opening `https://<site>/browse/<KEY>` in the browser with the same account |
| `issue get` fails with a scoped token | The token needs the `read:jira-work` scope |
| Unexpected account is used | `ATL_JIRA_API_TOKEN` overrides the keyring; check `atl auth status` → `token_source` |
