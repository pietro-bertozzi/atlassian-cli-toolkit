"""Application logic for Jira use cases."""

from __future__ import annotations

from atlassian_toolkit.core.client import JiraClient
from atlassian_toolkit.jira import api
from atlassian_toolkit.jira.models import CurrentUser


def get_current_user(client: JiraClient) -> CurrentUser:
    """Return the user the configured API token belongs to."""
    return CurrentUser.from_api(api.get_myself(client))
