"""Thin wrappers over Jira Cloud REST endpoints. No printing, no business logic."""

from __future__ import annotations

from typing import Any

from atlassian_toolkit.core.client import JiraClient
from atlassian_toolkit.core.errors import ApiError


def get_myself(client: JiraClient) -> dict[str, Any]:
    """``GET /rest/api/3/myself`` — the current user.

    Docs: https://developer.atlassian.com/cloud/jira/platform/rest/v3/api-group-myself/
    Required scope (scoped tokens): ``read:jira-user``.
    """
    data = client.get("/rest/api/3/myself")
    if not isinstance(data, dict):
        raise ApiError("Unexpected response from /rest/api/3/myself (expected a JSON object).")
    return data
