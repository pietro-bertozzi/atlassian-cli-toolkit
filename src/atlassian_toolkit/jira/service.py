"""Application logic for Jira use cases."""

from __future__ import annotations

from atlassian_toolkit.core.client import JiraClient
from atlassian_toolkit.jira import api
from atlassian_toolkit.jira.models import CurrentUser, Issue

# Fields requested for `atl jira issue get`. Asking only for these keeps the response small and
# avoids custom fields, whose ids differ per site.
ISSUE_FIELDS = (
    "summary",
    "status",
    "issuetype",
    "priority",
    "project",
    "assignee",
    "reporter",
    "parent",
    "labels",
    "created",
    "updated",
    "duedate",
    "resolution",
    "description",
)


def get_current_user(client: JiraClient) -> CurrentUser:
    """Return the user the configured API token belongs to."""
    return CurrentUser.from_api(api.get_myself(client))


def get_issue(client: JiraClient, issue_id_or_key: str, site: str) -> Issue:
    """Return one issue by key (e.g. ``DEMO-123``) or numeric id."""
    return Issue.from_api(api.get_issue(client, issue_id_or_key, ISSUE_FIELDS), site)
