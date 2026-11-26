"""``atl jira ...`` read commands against a mocked Jira (no network)."""

import json

import httpx
import pytest
from helpers import LOGIN, TOKEN, MemoryKeyring, route_jira, runner

from atlassian_toolkit.cli import app

ISSUE_BODY = {
    "id": "10001",
    "key": "DEMO-123",
    "fields": {
        "summary": "Fix the login page",
        "issuetype": {"name": "Bug"},
        "status": {"name": "To Do", "statusCategory": {"name": "To Do"}},
        "project": {"key": "DEMO"},
        "labels": [],
        "description": {
            "type": "doc",
            "version": 1,
            "content": [
                {
                    "type": "heading",
                    "attrs": {"level": 2},
                    "content": [{"type": "text", "text": "Goal"}],
                },
                {"type": "paragraph", "content": [{"type": "text", "text": "Make | it work"}]},
            ],
        },
    },
}


def test_issue_get_requests_explicit_fields(logged_in: MemoryKeyring, mock_jira) -> None:  # type: ignore[no-untyped-def]
    seen = mock_jira(httpx.Response(200, json=ISSUE_BODY))
    result = runner.invoke(app, ["-f", "json", "jira", "issue", "get", "DEMO-123"])
    assert result.exit_code == 0, result.output
    request = seen[0]
    assert request.url.path == "/rest/api/3/issue/DEMO-123"
    fields = request.url.params["fields"].split(",")
    assert "description" in fields
    assert "*all" not in fields
    assert not any(f.startswith("customfield_") for f in fields)


def test_issue_get_json_output(logged_in: MemoryKeyring, mock_jira) -> None:  # type: ignore[no-untyped-def]
    mock_jira(httpx.Response(200, json=ISSUE_BODY))
    result = runner.invoke(app, ["-f", "json", "jira", "issue", "get", "DEMO-123"])
    data = json.loads(result.stdout)
    assert list(data) == [
        "key", "id", "url", "summary", "issue_type", "status", "status_category",
        "status_category_key", "priority",
        "project_key", "parent_key", "assignee", "reporter", "labels", "resolution", "created",
        "updated", "due_date", "subtasks", "links", "transitions", "description", "extra_fields",
    ]  # fmt: skip
    assert data["url"] == "https://example.atlassian.net/browse/DEMO-123"
    assert data["description"] == "## Goal\n\nMake | it work"


def test_issue_get_encodes_the_key_in_the_path(logged_in: MemoryKeyring, mock_jira) -> None:  # type: ignore[no-untyped-def]
    seen = mock_jira(httpx.Response(200, json=ISSUE_BODY))
    runner.invoke(app, ["-f", "json", "jira", "issue", "get", "../myself?x=1"])
    assert seen[0].url.raw_path.startswith(b"/rest/api/3/issue/..%2Fmyself%3Fx%3D1?")


def test_issue_get_markdown_document(logged_in: MemoryKeyring, mock_jira) -> None:  # type: ignore[no-untyped-def]
    mock_jira(httpx.Response(200, json=ISSUE_BODY))
    result = runner.invoke(app, ["-f", "markdown", "jira", "issue", "get", "DEMO-123"])
    assert result.exit_code == 0, result.output
    out = result.stdout
    assert out.startswith("# DEMO-123: Fix the login page\n\n- **key**: DEMO-123\n")
    assert "- **description**" not in out
    assert out.rstrip().endswith("## Description\n\n## Goal\n\nMake | it work")


def test_issue_get_404_exits_5(logged_in: MemoryKeyring, mock_jira) -> None:  # type: ignore[no-untyped-def]
    body = {"errorMessages": ["Issue does not exist or you do not have permission to see it."]}
    mock_jira(httpx.Response(404, json=body))
    result = runner.invoke(app, ["jira", "issue", "get", "DEMO-999"])
    assert result.exit_code == 5
    assert "does not exist" in result.stderr
    assert result.stdout == ""


def test_issue_get_401_exits_4(logged_in: MemoryKeyring, mock_jira) -> None:  # type: ignore[no-untyped-def]
    mock_jira(httpx.Response(401))
    assert runner.invoke(app, ["jira", "issue", "get", "DEMO-1"]).exit_code == 4


def test_issue_get_url_uses_site_in_scoped_mode(memory_keyring: MemoryKeyring, mock_jira) -> None:  # type: ignore[no-untyped-def]
    login = [*LOGIN, "--mode", "scoped", "--cloud-id", "11111111-2222-3333-4444-555555555555"]
    assert runner.invoke(app, [*login, "--token-stdin"], input=TOKEN).exit_code == 0
    seen = mock_jira(httpx.Response(200, json=ISSUE_BODY))
    result = runner.invoke(app, ["-f", "json", "jira", "issue", "get", "DEMO-123"])
    assert result.exit_code == 0, result.output
    assert seen[0].url.host == "api.atlassian.com"
    assert json.loads(result.stdout)["url"] == "https://example.atlassian.net/browse/DEMO-123"


def _search_issue(n: int) -> dict:
    return {
        "id": str(10000 + n),
        "key": f"DEMO-{n}",
        "fields": {
            "summary": f"Issue {n}",
            "status": {"name": "To Do", "statusCategory": {"key": "new", "name": "To Do"}},
            "issuetype": {"name": "Task"},
            "priority": {"name": "Medium"},
            "assignee": {"displayName": "Alice Example"},
            "updated": "2026-01-10T09:00:00.000+0100",
        },
    }


@pytest.fixture
def paged_jira(monkeypatch: pytest.MonkeyPatch) -> list[httpx.Request]:
    """Serve 5 issues in pages of 2 (tokens 'p2', 'p3'), as /search/jql does."""
    seen: list[httpx.Request] = []
    pages = {None: ([1, 2], "p2"), "p2": ([3, 4], "p3"), "p3": ([5], None)}

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        numbers, next_token = pages[request.url.params.get("nextPageToken")]
        body: dict = {"issues": [_search_issue(n) for n in numbers], "isLast": next_token is None}
        if next_token:
            body["nextPageToken"] = next_token
        return httpx.Response(200, json=body)

    route_jira(monkeypatch, handler)
    return seen


def test_search_follows_next_page_token(logged_in: MemoryKeyring, paged_jira) -> None:  # type: ignore[no-untyped-def]
    result = runner.invoke(app, ["-f", "json", "jira", "search", "project = DEMO"])
    assert result.exit_code == 0, result.output
    data = json.loads(result.stdout)
    assert [d["key"] for d in data] == ["DEMO-1", "DEMO-2", "DEMO-3", "DEMO-4", "DEMO-5"]
    assert list(data[0]) == [
        "key", "summary", "status", "status_category", "status_category_key", "issue_type",
        "priority", "assignee",
        "updated", "url", "extra_fields",
    ]  # fmt: skip
    assert data[0]["url"] == "https://example.atlassian.net/browse/DEMO-1"
    assert data[0]["status_category_key"] == "new"
    first = paged_jira[0]
    assert first.url.path == "/rest/api/3/search/jql"
    assert first.url.params["jql"] == "project = DEMO"
    assert "summary" in first.url.params["fields"].split(",")
    assert "nextPageToken" not in first.url.params
    assert [r.url.params.get("nextPageToken") for r in paged_jira[1:]] == ["p2", "p3"]
    assert "more match" not in result.stderr


def test_search_limit_stops_early_and_warns(logged_in: MemoryKeyring, paged_jira) -> None:  # type: ignore[no-untyped-def]
    result = runner.invoke(app, ["-f", "json", "jira", "search", "project = DEMO", "--limit", "3"])
    assert result.exit_code == 0, result.output
    assert [d["key"] for d in json.loads(result.stdout)] == ["DEMO-1", "DEMO-2", "DEMO-3"]
    assert len(paged_jira) == 2
    assert paged_jira[1].url.params["maxResults"] == "1"
    assert "first 3 issues; more match" in result.stderr


def test_mine_uses_current_user_jql(logged_in: MemoryKeyring, paged_jira) -> None:  # type: ignore[no-untyped-def]
    result = runner.invoke(app, ["-f", "json", "jira", "mine"])
    assert result.exit_code == 0, result.output
    jql = paged_jira[0].url.params["jql"]
    assert "assignee = currentUser()" in jql
    assert "statusCategory != Done" in jql


def test_search_table_shows_selected_columns(logged_in: MemoryKeyring, paged_jira) -> None:  # type: ignore[no-untyped-def]
    result = runner.invoke(app, ["-f", "table", "jira", "search", "project = DEMO"])
    assert result.exit_code == 0, result.output
    assert "DEMO-5" in result.stdout
    assert "updated" not in result.stdout


def test_search_empty_result_is_empty_json_list(logged_in: MemoryKeyring, mock_jira) -> None:  # type: ignore[no-untyped-def]
    mock_jira(httpx.Response(200, json={"issues": [], "isLast": True}))
    result = runner.invoke(app, ["-f", "json", "jira", "search", "project = DEMO"])
    assert result.exit_code == 0
    assert json.loads(result.stdout) == []


def test_search_invalid_jql_exits_6_with_jira_message(logged_in: MemoryKeyring, mock_jira) -> None:  # type: ignore[no-untyped-def]
    body = {"errorMessages": ["Error in the JQL Query: Expecting a field name."]}
    mock_jira(httpx.Response(400, json=body))
    result = runner.invoke(app, ["jira", "search", "= nonsense"])
    assert result.exit_code == 6
    assert "Error in the JQL Query" in result.stderr
    assert result.stdout == ""


def _comment(n: int) -> dict:
    return {
        "id": str(n),
        "author": {"displayName": "Alice Example"},
        "created": f"2026-01-{n:02d}T09:00:00.000+0100",
        "updated": f"2026-01-{n:02d}T09:00:00.000+0100",
        "body": {
            "type": "doc",
            "version": 1,
            "content": [{"type": "paragraph", "content": [{"type": "text", "text": f"c{n}"}]}],
        },
    }


@pytest.fixture
def jira_with_comments(monkeypatch: pytest.MonkeyPatch) -> list[httpx.Request]:
    """Serve ISSUE_BODY and 5 comments in pages of at most 2 (offset pagination)."""
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        if request.url.path.endswith("/comment"):
            start = int(request.url.params["startAt"])
            size = min(2, int(request.url.params["maxResults"]))
            numbers = list(range(1, 6))[start : start + size]
            body = {
                "startAt": start,
                "maxResults": size,
                "total": 5,
                "comments": [_comment(n) for n in numbers],
            }
            return httpx.Response(200, json=body)
        return httpx.Response(200, json=ISSUE_BODY)

    route_jira(monkeypatch, handler)
    return seen


def test_comments_follow_start_at_pages(logged_in: MemoryKeyring, jira_with_comments) -> None:  # type: ignore[no-untyped-def]
    args = ["-f", "json", "jira", "issue", "get", "DEMO-123", "--comments"]
    result = runner.invoke(app, args)
    assert result.exit_code == 0, result.output
    data = json.loads(result.stdout)["comments"]
    assert [c["body"] for c in data] == ["c1", "c2", "c3", "c4", "c5"]
    assert list(data[0]) == ["id", "author", "created", "updated", "visibility", "body"]
    comment_requests = [r for r in jira_with_comments if r.url.path.endswith("/comment")]
    assert [r.url.params["startAt"] for r in comment_requests] == ["0", "2", "4"]
    assert comment_requests[0].url.path == "/rest/api/3/issue/DEMO-123/comment"
    assert comment_requests[0].url.params["orderBy"] == "created"
    assert "more exist" not in result.stderr


def test_comments_limit_and_newest_first(logged_in: MemoryKeyring, jira_with_comments) -> None:  # type: ignore[no-untyped-def]
    args = ["-f", "json", "jira", "issue", "get", "DEMO-123", "--comments", "-n", "3",
            "--newest-first"]  # fmt: skip
    result = runner.invoke(app, args)
    assert result.exit_code == 0, result.output
    assert len(json.loads(result.stdout)["comments"]) == 3
    assert jira_with_comments[1].url.params["orderBy"] == "-created"
    assert "first 3 comments; more exist" in result.stderr


def test_comments_markdown(logged_in: MemoryKeyring, jira_with_comments) -> None:  # type: ignore[no-untyped-def]
    args = ["-f", "markdown", "jira", "issue", "get", "DEMO-123", "--comments"]
    result = runner.invoke(app, args)
    assert result.exit_code == 0, result.output
    assert "## Comments\n\n### Alice Example · 2026-01-01T09:00:00.000+0100\n\nc1" in result.stdout


def test_issue_get_comments_json_has_issue_and_comments(
    logged_in: MemoryKeyring,
    jira_with_comments,  # type: ignore[no-untyped-def]
) -> None:
    args = ["-f", "json", "jira", "issue", "get", "DEMO-123", "--comments"]
    result = runner.invoke(app, args)
    assert result.exit_code == 0, result.output
    data = json.loads(result.stdout)
    assert data["key"] == "DEMO-123"
    assert data["description"] == "## Goal\n\nMake | it work"
    assert [c["body"] for c in data["comments"]] == ["c1", "c2", "c3", "c4", "c5"]
    assert list(data)[-1] == "comments"


def test_issue_get_comments_markdown_sections(logged_in: MemoryKeyring, jira_with_comments) -> None:  # type: ignore[no-untyped-def]
    args = ["-f", "markdown", "jira", "issue", "get", "DEMO-123", "--comments"]
    result = runner.invoke(app, args)
    assert result.exit_code == 0, result.output
    out = result.stdout
    assert out.startswith("# DEMO-123: Fix the login page")
    assert out.index("## Description") < out.index("## Comments")
    assert "### Alice Example · 2026-01-05T09:00:00.000+0100\n\nc5" in out
    assert "- **subtasks**" not in out


def test_issue_get_markdown_lists_subtasks_and_links(
    logged_in: MemoryKeyring,
    mock_jira,  # type: ignore[no-untyped-def]
) -> None:
    body = json.loads(json.dumps(ISSUE_BODY))
    body["fields"]["subtasks"] = [
        {"key": "DEMO-124", "fields": {"summary": "Write the fix", "status": {"name": "Done"}}}
    ]
    body["fields"]["issuelinks"] = [
        {
            "type": {"name": "Blocks", "inward": "is blocked by", "outward": "blocks"},
            "inwardIssue": {"key": "DEMO-9", "fields": {"summary": "Login API"}},
        }
    ]
    mock_jira(httpx.Response(200, json=body))
    result = runner.invoke(app, ["-f", "markdown", "jira", "issue", "get", "DEMO-123"])
    assert result.exit_code == 0, result.output
    assert "## Subtasks\n\n- DEMO-124 [Done] Write the fix" in result.stdout
    assert "## Links\n\n- is blocked by DEMO-9 Login API" in result.stdout
    table = runner.invoke(app, ["-f", "table", "jira", "issue", "get", "DEMO-123"])
    assert table.exit_code == 0, table.output
    assert "DEMO-124 [Done] Write the fix" in table.stdout


def _project(n: int) -> dict:
    return {
        "id": str(10000 + n),
        "key": f"P{n}",
        "name": f"Project {n}",
        "projectTypeKey": "software",
        "style": "classic" if n % 2 else "next-gen",
    }


@pytest.fixture
def jira_projects(monkeypatch: pytest.MonkeyPatch) -> list[httpx.Request]:
    """Serve 5 projects in pages of at most 2; a query matching nothing gets a 404."""
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        if request.url.params.get("query") == "nothing":
            return httpx.Response(404, json={"errorMessages": ["No projects found."]})
        start = int(request.url.params["startAt"])
        size = min(2, int(request.url.params["maxResults"]))
        values = [_project(n) for n in range(1, 6)][start : start + size]
        body = {"startAt": start, "total": 5, "values": values, "isLast": start + size >= 5}
        return httpx.Response(200, json=body)

    route_jira(monkeypatch, handler)
    return seen


def test_projects_pages_until_is_last(logged_in: MemoryKeyring, jira_projects) -> None:  # type: ignore[no-untyped-def]
    result = runner.invoke(app, ["-f", "json", "jira", "projects"])
    assert result.exit_code == 0, result.output
    data = json.loads(result.stdout)
    assert [p["key"] for p in data] == ["P1", "P2", "P3", "P4", "P5"]
    assert data[0] == {
        "key": "P1",
        "id": "10001",
        "name": "Project 1",
        "project_type": "software",
        "style": "classic",
        "url": "https://example.atlassian.net/browse/P1",
    }
    assert [r.url.params["startAt"] for r in jira_projects] == ["0", "2", "4"]
    assert jira_projects[0].url.path == "/rest/api/3/project/search"
    assert "query" not in jira_projects[0].url.params


def test_projects_query_and_limit(logged_in: MemoryKeyring, jira_projects) -> None:  # type: ignore[no-untyped-def]
    result = runner.invoke(app, ["-f", "json", "jira", "projects", "-q", "proj", "-n", "3"])
    assert result.exit_code == 0, result.output
    assert len(json.loads(result.stdout)) == 3
    assert jira_projects[0].url.params["query"] == "proj"
    assert "first 3 projects; more exist" in result.stderr


def test_projects_no_match_is_empty_list_not_404(logged_in: MemoryKeyring, jira_projects) -> None:  # type: ignore[no-untyped-def]
    result = runner.invoke(app, ["-f", "json", "jira", "projects", "-q", "nothing"])
    assert result.exit_code == 0, result.output
    assert json.loads(result.stdout) == []


FLOAT_TYPE = "com.atlassian.jira.plugin.system.customfieldtypes:float"


FIELDS_BODY = [
    {"id": "summary", "name": "Summary", "custom": False, "clauseNames": ["summary"],
     "schema": {"type": "string", "system": "summary"}},
    {"id": "customfield_10016", "name": "Story point estimate", "custom": True,
     "clauseNames": ["cf[10016]", "Story point estimate"],
     "schema": {"type": "number", "custom": "com.atlassian.jpo:jpo-custom-field-baseline",
                "customId": 10016}},
    {"id": "customfield_10050", "name": "Story Points", "custom": True,
     "clauseNames": ["cf[10050]", "Story Points"],
     "schema": {"type": "number", "custom": FLOAT_TYPE},
     "scope": {"type": "PROJECT", "project": {"id": "10002"}}},
    {"id": "labels", "name": "Labels", "custom": False, "clauseNames": ["labels"],
     "schema": {"type": "array", "items": "string", "system": "labels"}},
    {"id": "broken"},
]  # fmt: skip


def test_fields_search_matches_name_id_and_clause(logged_in: MemoryKeyring, mock_jira) -> None:  # type: ignore[no-untyped-def]
    seen = mock_jira(httpx.Response(200, json=FIELDS_BODY))
    result = runner.invoke(app, ["-f", "json", "jira", "fields", "--search", "STORY POINT"])
    assert result.exit_code == 0, result.output
    data = json.loads(result.stdout)
    assert [f["id"] for f in data] == ["customfield_10016", "customfield_10050"]
    assert data[1] == {
        "id": "customfield_10050",
        "name": "Story Points",
        "custom": True,
        "type": "number",
        "items": None,
        "custom_type": "com.atlassian.jira.plugin.system.customfieldtypes:float",
        "clause_names": ["cf[10050]", "Story Points"],
        "scope_project_id": "10002",
    }
    assert seen[0].url.path == "/rest/api/3/field"
    by_id = runner.invoke(app, ["-f", "json", "jira", "fields", "-s", "10016"])
    assert [f["id"] for f in json.loads(by_id.stdout)] == ["customfield_10016"]


def test_fields_custom_only_and_sorted(logged_in: MemoryKeyring, mock_jira) -> None:  # type: ignore[no-untyped-def]
    mock_jira(httpx.Response(200, json=FIELDS_BODY))
    result = runner.invoke(app, ["-f", "json", "jira", "fields"])
    names = [f["name"] for f in json.loads(result.stdout)]
    assert names == ["", "Labels", "Story point estimate", "Story Points", "Summary"]
    custom = runner.invoke(app, ["-f", "json", "jira", "fields", "--custom"])
    assert all(f["custom"] for f in json.loads(custom.stdout))


def test_fields_unexpected_response_exits_6(logged_in: MemoryKeyring, mock_jira) -> None:  # type: ignore[no-untyped-def]
    mock_jira(httpx.Response(200, json={"not": "a list"}))
    assert runner.invoke(app, ["jira", "fields"]).exit_code == 6


def test_issue_get_extra_fields(logged_in: MemoryKeyring, mock_jira) -> None:  # type: ignore[no-untyped-def]
    body = json.loads(json.dumps(ISSUE_BODY))
    body["fields"]["customfield_10016"] = 5
    body["fields"]["customfield_10020"] = [{"id": 1, "name": "Sprint 4", "state": "active"}]
    seen = mock_jira(httpx.Response(200, json=body))
    args = ["-f", "json", "jira", "issue", "get", "DEMO-123"]
    result = runner.invoke(app, [*args, "--field", "customfield_10016,customfield_10020"])
    assert result.exit_code == 0, result.output
    assert json.loads(result.stdout)["extra_fields"] == {
        "customfield_10016": 5,
        "customfield_10020": ["Sprint 4"],
    }
    fields = seen[0].url.params["fields"].split(",")
    assert fields[-2:] == ["customfield_10016", "customfield_10020"]
    md = runner.invoke(app, ["-f", "markdown", *args[2:], "--field", "customfield_10016"])
    assert "- **customfield_10016**: 5" in md.stdout
    assert "extra_fields" not in md.stdout


def test_search_extra_field_becomes_table_column(logged_in: MemoryKeyring, paged_jira) -> None:  # type: ignore[no-untyped-def]
    args = ["jira", "search", "project = DEMO", "--field", "customfield_10016"]
    table = runner.invoke(app, ["-f", "table", *args])
    assert table.exit_code == 0, table.output
    assert "customfield_10016" in table.stdout
    data = json.loads(runner.invoke(app, ["-f", "json", *args]).stdout)
    assert data[0]["extra_fields"] == {"customfield_10016": None}
    assert "customfield_10016" in paged_jira[0].url.params["fields"].split(",")


def test_field_option_rejects_bad_ids(logged_in: MemoryKeyring) -> None:
    result = runner.invoke(app, ["jira", "issue", "get", "DEMO-1", "--field", "a b"])
    assert result.exit_code == 2
    assert "not a field id" in result.output


def test_issue_get_without_comments_is_one_request(
    logged_in: MemoryKeyring,
    jira_with_comments,  # type: ignore[no-untyped-def]
) -> None:
    result = runner.invoke(app, ["-f", "json", "jira", "issue", "get", "DEMO-123"])
    assert result.exit_code == 0, result.output
    assert "comments" not in json.loads(result.stdout)
    assert len(jira_with_comments) == 1


def test_issue_get_comments_limit(logged_in: MemoryKeyring, jira_with_comments) -> None:  # type: ignore[no-untyped-def]
    args = ["-f", "json", "jira", "issue", "get", "DEMO-123", "--comments", "-n", "3"]
    result = runner.invoke(app, args)
    assert result.exit_code == 0, result.output
    assert len(json.loads(result.stdout)["comments"]) == 3
    assert "more exist" in result.stderr


@pytest.mark.parametrize("removed", ["context", "comments"])
def test_folded_issue_commands_are_gone(logged_in: MemoryKeyring, removed: str) -> None:
    assert runner.invoke(app, ["jira", "issue", removed, "DEMO-123"]).exit_code == 2


def test_issue_get_shows_possible_status_changes(logged_in: MemoryKeyring, mock_jira) -> None:  # type: ignore[no-untyped-def]
    body = {**ISSUE_BODY, "transitions": [
        {"id": "21", "name": "Send to review", "hasScreen": True,
         "to": {"name": "In Review", "statusCategory": {"key": "indeterminate"}}}]}  # fmt: skip
    seen = mock_jira(httpx.Response(200, json=body))
    result = runner.invoke(app, ["-f", "json", "jira", "issue", "get", "DEMO-123"])
    assert result.exit_code == 0, result.output
    assert seen[0].url.params["expand"] == "transitions"
    assert json.loads(result.stdout)["transitions"] == [
        {
            "id": "21",
            "name": "Send to review",
            "to_status": "In Review",
            "to_status_category_key": "indeterminate",
            "has_screen": True,
        }
    ]
    md = runner.invoke(app, ["-f", "markdown", "jira", "issue", "get", "DEMO-123"]).stdout
    assert "## Possible status changes\n\n- Send to review -> In Review (has a screen)" in md
    table = runner.invoke(app, ["-f", "table", "jira", "issue", "get", "DEMO-123"]).stdout
    assert "Send to review -> In Review" in table
