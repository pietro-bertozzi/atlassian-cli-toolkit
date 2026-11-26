"""Thin wrappers over Jira Cloud REST endpoints. No printing, no business logic."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any
from urllib.parse import quote

from atlassian_toolkit.core.client import JiraClient
from atlassian_toolkit.core.errors import ApiError, NotFoundError


def get_myself(client: JiraClient) -> dict[str, Any]:
    """``GET /rest/api/3/myself`` — the current user.

    Docs: https://developer.atlassian.com/cloud/jira/platform/rest/v3/api-group-myself/
    Required scope (scoped tokens): ``read:jira-user``.
    """
    return _expect_object(client.get("/rest/api/3/myself"), "/rest/api/3/myself")


def get_issue(
    client: JiraClient, issue_id_or_key: str, fields: Sequence[str], expand: str | None = None
) -> dict[str, Any]:
    """``GET /rest/api/3/issue/{issueIdOrKey}`` — one issue, limited to ``fields``.

    Docs: https://developer.atlassian.com/cloud/jira/platform/rest/v3/api-group-issues/#api-rest-api-3-issue-issueidorkey-get
    Required scope (scoped tokens): ``read:jira-work``. Jira answers 404 both when the issue
    does not exist and when the user may not see it. ``expand="transitions"`` adds the
    transitions available to the user (empty without *Transition issues*).
    """
    # Percent-encode the whole segment so user input cannot alter the request path.
    path = f"/rest/api/3/issue/{quote(issue_id_or_key, safe='')}"
    params = {"fields": ",".join(fields)}
    if expand:
        params["expand"] = expand
    return _expect_object(client.get(path, params=params), path)


def _expect_object(data: Any, path: str) -> dict[str, Any]:
    if not isinstance(data, dict):
        raise ApiError(f"Unexpected response from {path} (expected a JSON object).")
    return data


SEARCH_PAGE_SIZE = 100


def search_issues(
    client: JiraClient, jql: str, fields: Sequence[str], limit: int
) -> tuple[list[dict[str, Any]], bool]:
    """``GET /rest/api/3/search/jql`` — issues matching ``jql``, following ``nextPageToken``.

    Docs: https://developer.atlassian.com/cloud/jira/platform/rest/v3/api-group-issue-search/#api-rest-api-3-search-jql-get
    Required scope (scoped tokens): ``read:jira-work``. The JQL must be bounded (contain a
    search restriction). Returns at most ``limit`` issues and whether more were available.
    """
    path = "/rest/api/3/search/jql"
    issues: list[dict[str, Any]] = []
    token: str | None = None
    seen_tokens: set[str] = set()
    while len(issues) < limit:
        params: dict[str, Any] = {
            "jql": jql,
            "fields": ",".join(fields),
            "maxResults": min(SEARCH_PAGE_SIZE, limit - len(issues)),
        }
        if token:
            params["nextPageToken"] = token
        page = _expect_object(client.get(path, params=params), path)
        batch = page.get("issues")
        if not isinstance(batch, list):
            raise ApiError(f"Unexpected response from {path} (no 'issues' list).")
        issues.extend(item for item in batch if isinstance(item, dict))
        token = page.get("nextPageToken") if isinstance(page.get("nextPageToken"), str) else None
        # Stop on the last page; also guard against an empty page or a repeated token.
        if not token or not batch or token in seen_tokens:
            return issues[:limit], False
        seen_tokens.add(token)
    return issues[:limit], True


COMMENT_PAGE_SIZE = 100


def get_comments(
    client: JiraClient, issue_id_or_key: str, limit: int, newest_first: bool = False
) -> tuple[list[dict[str, Any]], bool]:
    """``GET /rest/api/3/issue/{issueIdOrKey}/comment`` — comments, following ``startAt`` pages.

    Docs: https://developer.atlassian.com/cloud/jira/platform/rest/v3/api-group-issue-comments/#api-rest-api-3-issue-issueidorkey-comment-get
    Required scope (scoped tokens): ``read:jira-work``. Only comments the user may see are
    returned. Returns at most ``limit`` comments and whether more were available.
    """
    path = f"/rest/api/3/issue/{quote(issue_id_or_key, safe='')}/comment"
    comments: list[dict[str, Any]] = []
    start = 0
    total: int | None = None
    while len(comments) < limit:
        params = {
            "startAt": start,
            "maxResults": min(COMMENT_PAGE_SIZE, limit - len(comments)),
            "orderBy": "-created" if newest_first else "created",
        }
        page = _expect_object(client.get(path, params=params), path)
        batch = page.get("comments")
        if not isinstance(batch, list):
            raise ApiError(f"Unexpected response from {path} (no 'comments' list).")
        comments.extend(item for item in batch if isinstance(item, dict))
        start += len(batch)
        raw_total = page.get("total")
        total = (
            raw_total if isinstance(raw_total, int) and not isinstance(raw_total, bool) else None
        )
        if not batch or (total is not None and start >= total):
            return comments[:limit], False
    return comments[:limit], total is None or start < total


PROJECT_PAGE_SIZE = 100


def list_projects(
    client: JiraClient, query: str | None, limit: int
) -> tuple[list[dict[str, Any]], bool]:
    """``GET /rest/api/3/project/search`` — projects the user can view, ordered by key.

    Docs: https://developer.atlassian.com/cloud/jira/platform/rest/v3/api-group-projects/#api-rest-api-3-project-search-get
    Required scope (scoped tokens): ``read:jira-work``. ``query`` matches key or name (case
    insensitive). Offset pagination (``startAt``, at most 100 per page) until ``isLast``.
    Jira answers 404 when no project matches; that is returned as an empty list.
    """
    path = "/rest/api/3/project/search"
    projects: list[dict[str, Any]] = []
    start = 0
    while len(projects) < limit:
        params: dict[str, Any] = {
            "startAt": start,
            "maxResults": min(PROJECT_PAGE_SIZE, limit - len(projects)),
            "orderBy": "key",
        }
        if query:
            params["query"] = query
        try:
            page = _expect_object(client.get(path, params=params), path)
        except NotFoundError:
            return projects, False
        batch = page.get("values")
        if not isinstance(batch, list):
            raise ApiError(f"Unexpected response from {path} (no 'values' list).")
        projects.extend(item for item in batch if isinstance(item, dict))
        start += len(batch)
        if not batch or page.get("isLast") is True:
            return projects[:limit], False
    return projects[:limit], True


def get_fields(client: JiraClient) -> list[dict[str, Any]]:
    """``GET /rest/api/3/field`` — all system and custom fields the user can see (no paging).

    Docs: https://developer.atlassian.com/cloud/jira/platform/rest/v3/api-group-issue-fields/#api-rest-api-3-field-get
    Required scope (scoped tokens): ``read:jira-work``. No permission is required.
    """
    path = "/rest/api/3/field"
    data = client.get(path)
    if not isinstance(data, list):
        raise ApiError(f"Unexpected response from {path} (expected a JSON list).")
    return [item for item in data if isinstance(item, dict)]


# --- write endpoints --------------------------------------------------------------------------
# Each needs a token allowed to write (classic token: the user's own permissions; scoped token:
# the ``write:jira-work`` scope) and the Jira project permission named in its docstring.


def add_comment(
    client: JiraClient, issue_id_or_key: str, body_adf: dict[str, Any]
) -> dict[str, Any]:
    """``POST /rest/api/3/issue/{issueIdOrKey}/comment`` — add a comment (``body`` in ADF).

    Docs: https://developer.atlassian.com/cloud/jira/platform/rest/v3/api-group-issue-comments/#api-rest-api-3-issue-issueidorkey-comment-post
    Permission: *Add comments*. Returns the created ``Comment``.
    """
    path = f"/rest/api/3/issue/{quote(issue_id_or_key, safe='')}/comment"
    return _expect_object(client.post(path, {"body": body_adf}), path)


def get_transitions(client: JiraClient, issue_id_or_key: str) -> list[dict[str, Any]]:
    """``GET /rest/api/3/issue/{issueIdOrKey}/transitions`` — moves available right now.

    Docs: https://developer.atlassian.com/cloud/jira/platform/rest/v3/api-group-issues/#api-rest-api-3-issue-issueidorkey-transitions-get
    Read-only (``read:jira-work``). Without *Transition issues* the list is empty.
    """
    path = f"/rest/api/3/issue/{quote(issue_id_or_key, safe='')}/transitions"
    data = _expect_object(client.get(path), path)
    transitions = data.get("transitions")
    if not isinstance(transitions, list):
        raise ApiError(f"Unexpected response from {path} (no 'transitions' list).")
    return [item for item in transitions if isinstance(item, dict)]


def transition_issue(client: JiraClient, issue_id_or_key: str, transition_id: str) -> None:
    """``POST /rest/api/3/issue/{issueIdOrKey}/transitions`` — perform a transition (204).

    Docs: https://developer.atlassian.com/cloud/jira/platform/rest/v3/api-group-issues/#api-rest-api-3-issue-issueidorkey-transitions-post
    Permission: *Transition issues*. Screen fields are not sent: a transition whose screen
    requires fields is rejected by Jira with HTTP 400.
    """
    path = f"/rest/api/3/issue/{quote(issue_id_or_key, safe='')}/transitions"
    client.post(path, {"transition": {"id": transition_id}})


def assign_issue(client: JiraClient, issue_id_or_key: str, account_id: str | None) -> None:
    """``PUT /rest/api/3/issue/{issueIdOrKey}/assignee`` — assign (None = unassign) (204).

    Docs: https://developer.atlassian.com/cloud/jira/platform/rest/v3/api-group-issues/#api-rest-api-3-issue-issueidorkey-assignee-put
    Permission: *Assign issues*.
    """
    path = f"/rest/api/3/issue/{quote(issue_id_or_key, safe='')}/assignee"
    client.put(path, {"accountId": account_id})


def find_assignable_users(
    client: JiraClient, issue_id_or_key: str, query: str, limit: int = 20
) -> list[dict[str, Any]]:
    """``GET /rest/api/3/user/assignable/search`` — users who can be assigned to the issue.

    Docs: https://developer.atlassian.com/cloud/jira/platform/rest/v3/api-group-user-search/#api-rest-api-3-user-assignable-search-get
    Scope: ``read:jira-user``. ``query`` matches display name or email (prefix match).
    """
    path = "/rest/api/3/user/assignable/search"
    params = {"issueKey": issue_id_or_key, "query": query, "maxResults": limit}
    data = client.get(path, params=params)
    if not isinstance(data, list):
        raise ApiError(f"Unexpected response from {path} (expected a JSON list).")
    return [item for item in data if isinstance(item, dict)]
