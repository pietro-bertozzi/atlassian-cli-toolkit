"""Application logic for Jira use cases."""

from __future__ import annotations

from collections.abc import Sequence

from atlassian_toolkit.core.client import JiraClient
from atlassian_toolkit.jira import api
from atlassian_toolkit.jira.models import (
    Comment,
    CurrentUser,
    Field,
    Issue,
    IssueSummary,
    Project,
)

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
    "subtasks",
    "issuelinks",
    "description",
)

# Fields requested per issue in search results (no description: keeps pages small).
SEARCH_FIELDS = ("summary", "status", "issuetype", "priority", "assignee", "updated")

# "My open work": assigned to the token's user, not in a Done-category status, newest first.
MY_OPEN_ISSUES_JQL = "assignee = currentUser() AND statusCategory != Done ORDER BY updated DESC"


def get_current_user(client: JiraClient) -> CurrentUser:
    """Return the user the configured API token belongs to."""
    return CurrentUser.from_api(api.get_myself(client))


def get_issue(
    client: JiraClient, issue_id_or_key: str, site: str, extra_fields: Sequence[str] = ()
) -> Issue:
    """Return one issue by key (e.g. ``DEMO-123``) or numeric id.

    ``extra_fields`` are additional field ids (e.g. ``customfield_10016``) to include.
    """
    raw = api.get_issue(client, issue_id_or_key, _with_extra(ISSUE_FIELDS, extra_fields))
    return Issue.from_api(raw, site, extra_fields)


def search_issues(
    client: JiraClient, jql: str, site: str, limit: int, extra_fields: Sequence[str] = ()
) -> tuple[list[IssueSummary], bool]:
    """Run a JQL search; return up to ``limit`` issues and whether more were available."""
    fields = _with_extra(SEARCH_FIELDS, extra_fields)
    raw, more = api.search_issues(client, jql, fields, limit)
    return [IssueSummary.from_api(item, site, extra_fields) for item in raw], more


def _with_extra(base: Sequence[str], extra: Sequence[str]) -> tuple[str, ...]:
    """``base`` plus the extra field ids not already in it (order kept)."""
    return (*base, *(field_id for field_id in extra if field_id not in base))


def get_comments(
    client: JiraClient, issue_id_or_key: str, limit: int, newest_first: bool = False
) -> tuple[list[Comment], bool]:
    """Return up to ``limit`` comments (oldest first by default) and whether more exist."""
    raw, more = api.get_comments(client, issue_id_or_key, limit, newest_first)
    return [Comment.from_api(item) for item in raw], more


def list_projects(
    client: JiraClient, site: str, query: str | None, limit: int
) -> tuple[list[Project], bool]:
    """Return up to ``limit`` viewable projects (optionally matching ``query``)."""
    raw, more = api.list_projects(client, query, limit)
    return [Project.from_api(item, site) for item in raw], more


def find_fields(client: JiraClient, search: str | None, custom_only: bool) -> list[Field]:
    """Return fields matching ``search`` (name, id or JQL name), sorted by name then id."""
    fields = [Field.from_api(item) for item in api.get_fields(client)]
    if custom_only:
        fields = [f for f in fields if f.custom]
    if search:
        fields = [f for f in fields if f.matches(search)]
    return sorted(fields, key=lambda f: (f.name.casefold(), f.id))
