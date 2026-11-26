"""Application logic for Jira use cases."""

from __future__ import annotations

from collections.abc import Sequence

from atlassian_toolkit.core.client import JiraClient
from atlassian_toolkit.core.errors import UsageError
from atlassian_toolkit.jira import api
from atlassian_toolkit.jira.adf_write import markdown_to_adf
from atlassian_toolkit.jira.models import (
    Comment,
    CurrentUser,
    Field,
    Issue,
    IssueSummary,
    Project,
    Transition,
    UserRef,
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
    fields = _with_extra(ISSUE_FIELDS, extra_fields)
    raw = api.get_issue(client, issue_id_or_key, fields, expand="transitions")
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


# --- writes -----------------------------------------------------------------------------------


def comment_request(markdown: str) -> dict[str, object]:
    """The JSON body sent to add a comment written in Markdown."""
    return {"body": markdown_to_adf(markdown)}


def add_comment(client: JiraClient, issue_id_or_key: str, markdown: str) -> Comment:
    """Add a comment written in Markdown (converted to ADF) and return it."""
    return Comment.from_api(api.add_comment(client, issue_id_or_key, markdown_to_adf(markdown)))


def list_transitions(client: JiraClient, issue_id_or_key: str) -> list[Transition]:
    """Return the transitions available on the issue right now."""
    return [Transition.from_api(item) for item in api.get_transitions(client, issue_id_or_key)]


def choose_transition(transitions: Sequence[Transition], target: str) -> Transition:
    """Pick the transition named ``target`` or leading to the status ``target`` (any case).

    A transition name wins over a status name. Raises UsageError when nothing or more than one
    transition matches, listing what is available.
    """
    wanted = target.strip().casefold()
    by_name = [t for t in transitions if t.name.casefold() == wanted]
    matches = by_name or [t for t in transitions if (t.to_status or "").casefold() == wanted]
    if len(matches) == 1:
        return matches[0]
    options = "; ".join(f"{t.name!r} -> {t.to_status}" for t in transitions) or "none"
    if not matches:
        raise UsageError(f"No transition named or leading to {target!r}. Available: {options}.")
    raise UsageError(f"{target!r} matches several transitions; use one of: {options}.")


def transition_issue(client: JiraClient, issue_id_or_key: str, transition_id: str) -> None:
    """Perform the transition with id ``transition_id`` (from :func:`choose_transition`)."""
    api.transition_issue(client, issue_id_or_key, transition_id)


def find_assignee(client: JiraClient, issue_id_or_key: str, who: str) -> UserRef:
    """Resolve ``who`` to one assignable user: ``me``, or a name/email to search.

    Exactly one candidate is required: an exact (case-insensitive) display name or email match
    among the results wins; otherwise a single result. Raises UsageError otherwise.
    """
    if who.strip().casefold() == "me":
        return UserRef.from_api(api.get_myself(client))
    users = [
        UserRef.from_api(item) for item in api.find_assignable_users(client, issue_id_or_key, who)
    ]
    users = [u for u in users if u.active and u.account_id]
    wanted = who.strip().casefold()
    exact = [u for u in users if wanted in {u.display_name.casefold(), (u.email or "").casefold()}]
    candidates = exact or users
    if len(candidates) == 1:
        return candidates[0]
    if not candidates:
        raise UsageError(f"No assignable user matches {who!r} for this issue.")
    names = "; ".join(f"{u.display_name} ({u.account_id})" for u in candidates[:10])
    raise UsageError(
        f"{who!r} matches several users: {names}. Use a more specific name or --account-id."
    )


def assign_issue(client: JiraClient, issue_id_or_key: str, account_id: str | None) -> None:
    """Assign the issue to ``account_id`` (None = unassign)."""
    api.assign_issue(client, issue_id_or_key, account_id)
