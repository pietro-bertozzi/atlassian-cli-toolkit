"""Data we expose from Jira. JSON key names (the dataclass field names) are a stable contract."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import asdict, dataclass
from typing import Any
from urllib.parse import quote

from atlassian_toolkit.jira.adf import adf_to_markdown


@dataclass(frozen=True)
class CurrentUser:
    """The user the API token authenticates as (``GET /rest/api/3/myself``).

    ``email``, ``time_zone`` and ``account_type`` may be None: Jira omits or nulls some fields
    depending on the user's Atlassian Account privacy settings.
    """

    account_id: str
    display_name: str
    email: str | None
    active: bool
    time_zone: str | None
    account_type: str | None

    @classmethod
    def from_api(cls, data: Mapping[str, Any]) -> CurrentUser:
        """Build from the raw ``User`` object returned by the API."""
        return cls(
            account_id=data.get("accountId") or "",
            display_name=data.get("displayName") or "",
            email=data.get("emailAddress") or None,
            active=bool(data.get("active")),
            time_zone=data.get("timeZone") or None,
            account_type=data.get("accountType") or None,
        )

    def to_record(self) -> dict[str, Any]:
        """Return the record rendered by the output layer."""
        return asdict(self)


@dataclass(frozen=True)
class IssueRef:
    """A related issue embedded in another issue's data (e.g. a subtask)."""

    key: str
    summary: str
    status: str | None
    status_category_key: str | None
    issue_type: str | None

    @classmethod
    def from_api(cls, data: Mapping[str, Any]) -> IssueRef:
        """Build from a subtask or ``LinkedIssue`` object (``key`` + a few ``fields``)."""
        fields = _mapping(data.get("fields"))
        return cls(
            key=_str(data.get("key")) or "",
            summary=_str(fields.get("summary")) or "",
            status=_nested(fields, "status", "name"),
            status_category_key=_nested(_mapping(fields.get("status")), "statusCategory", "key"),
            issue_type=_nested(fields, "issuetype", "name"),
        )


@dataclass(frozen=True)
class IssueLink(IssueRef):
    """A link to another issue, described from this issue's side.

    ``relation`` is Jira's wording for the link type in that direction, e.g. ``blocks`` (this
    issue blocks ``key``) or ``is blocked by`` (``key`` blocks this issue).
    """

    relation: str = ""


@dataclass(frozen=True)
class Comment:
    """One issue comment. ``body`` is Markdown converted from ADF.

    ``visibility`` is the group or role the comment is restricted to, or None when it is
    visible to everyone who can see the issue.
    """

    id: str
    author: str | None
    created: str | None
    updated: str | None
    visibility: str | None
    body: str

    @classmethod
    def from_api(cls, data: Mapping[str, Any]) -> Comment:
        """Build from a ``Comment`` object of ``GET /rest/api/3/issue/{key}/comment``."""
        return cls(
            id=_str(data.get("id")) or "",
            author=_nested(data, "author", "displayName"),
            created=_str(data.get("created")),
            updated=_str(data.get("updated")),
            visibility=_nested(data, "visibility", "value"),
            body=adf_to_markdown(data.get("body")),
        )

    def to_record(self) -> dict[str, Any]:
        """Return the record rendered by the output layer."""
        return asdict(self)


@dataclass(frozen=True)
class Issue:
    """One Jira issue (``GET /rest/api/3/issue/{issueIdOrKey}``), with core fields only.

    ``status_category`` is the category name as Jira shows it (translated into the user's
    language); ``status_category_key`` is the language-independent key (e.g. ``new``).
    ``subtasks`` and ``links`` list related issues; ``description`` is Markdown converted from
    Jira's ADF rich text. Optional fields
    (priority, parent, assignee, ...) are None when unset or hidden from the user.
    """

    key: str
    id: str
    url: str
    summary: str
    issue_type: str | None
    status: str | None
    status_category: str | None
    status_category_key: str | None
    priority: str | None
    project_key: str | None
    parent_key: str | None
    assignee: str | None
    reporter: str | None
    labels: list[str]
    resolution: str | None
    created: str | None
    updated: str | None
    due_date: str | None
    subtasks: list[IssueRef]
    links: list[IssueLink]
    description: str | None

    @classmethod
    def from_api(cls, data: Mapping[str, Any], site: str) -> Issue:
        """Build from the raw ``IssueBean``; ``site`` (e.g. example.atlassian.net) makes ``url``."""
        fields = _mapping(data.get("fields"))
        key = _str(data.get("key")) or ""
        status = _mapping(fields.get("status"))
        labels = fields.get("labels")
        return cls(
            key=key,
            id=_str(data.get("id")) or "",
            url=f"https://{site}/browse/{quote(key, safe='')}",
            summary=_str(fields.get("summary")) or "",
            issue_type=_nested(fields, "issuetype", "name"),
            status=_nested(fields, "status", "name"),
            status_category=_nested(status, "statusCategory", "name"),
            status_category_key=_nested(status, "statusCategory", "key"),
            priority=_nested(fields, "priority", "name"),
            project_key=_nested(fields, "project", "key"),
            parent_key=_nested(fields, "parent", "key"),
            assignee=_nested(fields, "assignee", "displayName"),
            reporter=_nested(fields, "reporter", "displayName"),
            labels=[x for x in labels if isinstance(x, str)] if isinstance(labels, list) else [],
            resolution=_nested(fields, "resolution", "name"),
            created=_str(fields.get("created")),
            updated=_str(fields.get("updated")),
            due_date=_str(fields.get("duedate")),
            subtasks=[IssueRef.from_api(item) for item in _mappings(fields.get("subtasks"))],
            links=_links(fields.get("issuelinks")),
            description=adf_to_markdown(fields.get("description")) or None,
        )

    def to_record(self) -> dict[str, Any]:
        """Return the record rendered by the output layer."""
        return asdict(self)


@dataclass(frozen=True)
class IssueSummary:
    """One row of a JQL search result: the fields needed to scan a list of issues."""

    key: str
    summary: str
    status: str | None
    status_category: str | None
    status_category_key: str | None
    issue_type: str | None
    priority: str | None
    assignee: str | None
    updated: str | None
    url: str

    @classmethod
    def from_api(cls, data: Mapping[str, Any], site: str) -> IssueSummary:
        """Build from one ``IssueBean`` of a search response."""
        fields = _mapping(data.get("fields"))
        key = _str(data.get("key")) or ""
        return cls(
            key=key,
            summary=_str(fields.get("summary")) or "",
            status=_nested(fields, "status", "name"),
            status_category=_nested(_mapping(fields.get("status")), "statusCategory", "name"),
            status_category_key=_nested(_mapping(fields.get("status")), "statusCategory", "key"),
            issue_type=_nested(fields, "issuetype", "name"),
            priority=_nested(fields, "priority", "name"),
            assignee=_nested(fields, "assignee", "displayName"),
            updated=_str(fields.get("updated")),
            url=f"https://{site}/browse/{quote(key, safe='')}",
        )

    def to_record(self) -> dict[str, Any]:
        """Return the record rendered by the output layer."""
        return asdict(self)


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _mappings(value: Any) -> list[Mapping[str, Any]]:
    """Return the mapping items of ``value`` if it is a list, else an empty list."""
    return [item for item in value if isinstance(item, Mapping)] if isinstance(value, list) else []


def _links(raw: Any) -> list[IssueLink]:
    """Convert ``fields.issuelinks``: each link holds either ``outwardIssue`` or ``inwardIssue``.

    With ``outwardIssue`` this issue is the source, so the type's ``outward`` wording applies
    ("blocks"); with ``inwardIssue`` the other issue is the source ("is blocked by").
    """
    links = []
    for link in _mappings(raw):
        link_type = _mapping(link.get("type"))
        outward, inward = link.get("outwardIssue"), link.get("inwardIssue")
        if isinstance(outward, Mapping):
            other, relation = outward, _str(link_type.get("outward"))
        elif isinstance(inward, Mapping):
            other, relation = inward, _str(link_type.get("inward"))
        else:
            continue
        ref = IssueRef.from_api(other)
        relation = relation or _str(link_type.get("name")) or "linked to"
        links.append(IssueLink(**asdict(ref), relation=relation))
    return links


def _str(value: Any) -> str | None:
    return value if isinstance(value, str) and value else None


def _nested(parent: Mapping[str, Any], name: str, attr: str) -> str | None:
    """Return ``parent[name][attr]`` as a string, or None when missing/null/not a string."""
    return _str(_mapping(parent.get(name)).get(attr))
