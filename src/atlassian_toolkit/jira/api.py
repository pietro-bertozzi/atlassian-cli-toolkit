"""Thin wrappers over Jira Cloud REST endpoints. No printing, no business logic."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any
from urllib.parse import quote

from atlassian_toolkit.core.client import JiraClient
from atlassian_toolkit.core.errors import ApiError


def get_myself(client: JiraClient) -> dict[str, Any]:
    """``GET /rest/api/3/myself`` — the current user.

    Docs: https://developer.atlassian.com/cloud/jira/platform/rest/v3/api-group-myself/
    Required scope (scoped tokens): ``read:jira-user``.
    """
    return _expect_object(client.get("/rest/api/3/myself"), "/rest/api/3/myself")


def get_issue(client: JiraClient, issue_id_or_key: str, fields: Sequence[str]) -> dict[str, Any]:
    """``GET /rest/api/3/issue/{issueIdOrKey}`` — one issue, limited to ``fields``.

    Docs: https://developer.atlassian.com/cloud/jira/platform/rest/v3/api-group-issues/#api-rest-api-3-issue-issueidorkey-get
    Required scope (scoped tokens): ``read:jira-work``. Jira answers 404 both when the issue
    does not exist and when the user may not see it.
    """
    # Percent-encode the whole segment so user input cannot alter the request path.
    path = f"/rest/api/3/issue/{quote(issue_id_or_key, safe='')}"
    return _expect_object(client.get(path, params={"fields": ",".join(fields)}), path)


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
