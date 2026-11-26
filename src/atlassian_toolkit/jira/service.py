"""Application logic for Jira use cases."""

from __future__ import annotations

from atlassian_toolkit.core.client import JiraClient
from atlassian_toolkit.jira import api
from atlassian_toolkit.jira.models import CurrentUser, Issue, IssueSummary

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

# Fields requested per issue in search results (no description: keeps pages small).
SEARCH_FIELDS = ("summary", "status", "issuetype", "priority", "assignee", "updated")

# "My open work": assigned to the token's user, not in a Done-category status, newest first.
MY_OPEN_ISSUES_JQL = "assignee = currentUser() AND statusCategory != Done ORDER BY updated DESC"


def get_current_user(client: JiraClient) -> CurrentUser:
    """Return the user the configured API token belongs to."""
    return CurrentUser.from_api(api.get_myself(client))


def get_issue(client: JiraClient, issue_id_or_key: str, site: str) -> Issue:
    """Return one issue by key (e.g. ``DEMO-123``) or numeric id."""
    return Issue.from_api(api.get_issue(client, issue_id_or_key, ISSUE_FIELDS), site)


def search_issues(
    client: JiraClient, jql: str, site: str, limit: int
) -> tuple[list[IssueSummary], bool]:
    """Run a JQL search; return up to ``limit`` issues and whether more were available."""
    raw, more = api.search_issues(client, jql, SEARCH_FIELDS, limit)
    return [IssueSummary.from_api(item, site) for item in raw], more
