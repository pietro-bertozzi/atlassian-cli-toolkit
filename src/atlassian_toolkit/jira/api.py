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
