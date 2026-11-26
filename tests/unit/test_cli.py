import base64
import json
from collections.abc import Callable
from pathlib import Path

import httpx
import pytest
from conftest import MemoryKeyring
from typer.testing import CliRunner

from atlassian_toolkit.cli import app
from atlassian_toolkit.core.client import JiraClient
from atlassian_toolkit.core.config import default_config_path
from atlassian_toolkit.jira import commands as jira_commands

TOKEN = "fake-token-value"
LOGIN = [
    "auth",
    "login",
    "--site",
    "https://Example.atlassian.net/",
    "--email",
    "alice@example.com",
]
ME_BODY = {
    "accountId": "abc123",
    "displayName": "Alice Example",
    "emailAddress": "alice@example.com",
    "active": True,
    "timeZone": "Europe/Rome",
    "accountType": "atlassian",
}

runner = CliRunner()


@pytest.fixture
def logged_in(memory_keyring: MemoryKeyring) -> MemoryKeyring:
    result = runner.invoke(app, [*LOGIN, "--token-stdin"], input=TOKEN + "\n")
    assert result.exit_code == 0, result.output
    return memory_keyring


@pytest.fixture
def mock_jira(monkeypatch: pytest.MonkeyPatch) -> Callable[[httpx.Response], list[httpx.Request]]:
    """Route JiraClient through a MockTransport returning the given response."""

    def install(response: httpx.Response) -> list[httpx.Request]:
        seen: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            seen.append(request)
            return response

        def factory(profile, token):  # type: ignore[no-untyped-def]
            return JiraClient(profile, token, transport=httpx.MockTransport(handler))

        monkeypatch.setattr(jira_commands, "JiraClient", factory)
        return seen

    return install


def test_version() -> None:
    result = runner.invoke(app, ["--version"])
    assert result.exit_code == 0
    assert result.stdout.startswith("atl ")


def test_login_with_stdin_stores_token_in_keyring_not_in_config(
    logged_in: MemoryKeyring,
) -> None:
    assert logged_in.store == {("atl-jira", "default"): TOKEN}
    config_text = default_config_path().read_text()
    assert TOKEN not in config_text
    assert 'site = "example.atlassian.net"' in config_text  # normalized
    assert 'default_profile = "default"' in config_text


def test_login_prompts_for_hidden_token(memory_keyring: MemoryKeyring) -> None:
    result = runner.invoke(app, ["-p", "work", *LOGIN], input=TOKEN + "\n")
    assert result.exit_code == 0, result.output
    assert memory_keyring.store == {("atl-jira", "work"): TOKEN}
    assert TOKEN not in result.output


def test_login_token_stdin_requires_site_and_email(memory_keyring: MemoryKeyring) -> None:
    result = runner.invoke(app, ["auth", "login", "--token-stdin"], input=TOKEN)
    assert result.exit_code == 3
    assert memory_keyring.store == {}


def test_login_scoped_requires_cloud_id_with_stdin(memory_keyring: MemoryKeyring) -> None:
    result = runner.invoke(app, [*LOGIN, "--mode", "scoped", "--token-stdin"], input=TOKEN)
    assert result.exit_code == 3


def test_login_without_keyring_fails_and_writes_no_config(no_keyring: None) -> None:
    result = runner.invoke(app, [*LOGIN, "--token-stdin"], input=TOKEN)
    assert result.exit_code == 3
    assert "ATL_JIRA_API_TOKEN" in result.stderr
    assert not default_config_path().exists()


def test_login_rejects_unknown_mode(memory_keyring: MemoryKeyring) -> None:
    result = runner.invoke(app, [*LOGIN, "--mode", "bogus", "--token-stdin"], input=TOKEN)
    assert result.exit_code == 2


def test_status_json_never_shows_token(logged_in: MemoryKeyring) -> None:
    result = runner.invoke(app, ["-f", "json", "auth", "status"])
    assert result.exit_code == 0, result.output
    data = json.loads(result.stdout)
    assert data["profile"] == "default"
    assert data["site"] == "example.atlassian.net"
    assert data["token_source"] == "keyring"
    assert TOKEN not in result.output


def test_status_without_profile_is_config_error(memory_keyring: MemoryKeyring) -> None:
    result = runner.invoke(app, ["auth", "status"])
    assert result.exit_code == 3
    assert "atl auth login" in result.stderr
    assert result.stdout == ""


def test_logout_removes_token_and_profile(logged_in: MemoryKeyring) -> None:
    result = runner.invoke(app, ["auth", "logout"])
    assert result.exit_code == 0, result.output
    assert logged_in.store == {}
    assert runner.invoke(app, ["auth", "status"]).exit_code == 3


def test_jira_me_json(logged_in: MemoryKeyring, mock_jira) -> None:  # type: ignore[no-untyped-def]
    seen = mock_jira(httpx.Response(200, json=ME_BODY))
    result = runner.invoke(app, ["-f", "json", "jira", "me"])
    assert result.exit_code == 0, result.output
    assert json.loads(result.stdout) == {
        "account_id": "abc123",
        "display_name": "Alice Example",
        "email": "alice@example.com",
        "active": True,
        "time_zone": "Europe/Rome",
        "account_type": "atlassian",
    }
    assert str(seen[0].url) == "https://example.atlassian.net/rest/api/3/myself"


def test_jira_me_defaults_to_json_when_not_a_tty(logged_in: MemoryKeyring, mock_jira) -> None:  # type: ignore[no-untyped-def]
    mock_jira(httpx.Response(200, json=ME_BODY))
    result = runner.invoke(app, ["jira", "me"])
    assert json.loads(result.stdout)["account_id"] == "abc123"


def test_jira_me_tolerates_hidden_fields(logged_in: MemoryKeyring, mock_jira) -> None:  # type: ignore[no-untyped-def]
    mock_jira(httpx.Response(200, json={"accountId": "abc123", "displayName": "A", "active": True}))
    data = json.loads(runner.invoke(app, ["-f", "json", "jira", "me"]).stdout)
    assert data["email"] is None
    assert data["time_zone"] is None


def test_jira_me_401_exits_4_with_message_on_stderr(logged_in: MemoryKeyring, mock_jira) -> None:  # type: ignore[no-untyped-def]
    mock_jira(httpx.Response(401))
    result = runner.invoke(app, ["jira", "me"])
    assert result.exit_code == 4
    assert "expired or revoked" in result.stderr
    assert result.stdout == ""
    assert TOKEN not in result.output


def test_jira_me_without_profile_exits_3(memory_keyring: MemoryKeyring) -> None:
    assert runner.invoke(app, ["jira", "me"]).exit_code == 3


def test_jira_me_uses_env_token_over_keyring(
    logged_in: MemoryKeyring,
    mock_jira,
    monkeypatch: pytest.MonkeyPatch,  # type: ignore[no-untyped-def]
) -> None:
    seen = mock_jira(httpx.Response(200, json=ME_BODY))
    monkeypatch.setenv("ATL_JIRA_API_TOKEN", "env-token")
    runner.invoke(app, ["jira", "me"])
    assert base64.b64decode(seen[0].headers["Authorization"].split()[1]) == (
        b"alice@example.com:env-token"
    )


def test_config_dir_override_is_used(tmp_path: Path, logged_in: MemoryKeyring) -> None:
    assert default_config_path() == tmp_path / "config" / "config.toml"


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
        "updated", "due_date", "subtasks", "links", "description",
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


def test_login_with_token_file_stores_token_and_deletes_file(
    memory_keyring: MemoryKeyring, tmp_path: Path
) -> None:
    token_file = tmp_path / "token.txt"
    token_file.write_text("\ufeff" + TOKEN + "\r\n", encoding="utf-8")  # BOM + CRLF, as Notepad
    result = runner.invoke(app, [*LOGIN, "--token-file", str(token_file)])
    assert result.exit_code == 0, result.output
    assert memory_keyring.store == {("atl-jira", "default"): TOKEN}
    assert not token_file.exists()
    assert TOKEN not in result.output
    assert TOKEN not in default_config_path().read_text()


def test_login_token_file_missing_is_config_error(
    memory_keyring: MemoryKeyring, tmp_path: Path
) -> None:
    result = runner.invoke(app, [*LOGIN, "--token-file", str(tmp_path / "nope.txt")])
    assert result.exit_code == 3
    assert "not found" in result.stderr
    assert memory_keyring.store == {}


def test_login_token_file_keeps_file_when_keyring_fails(no_keyring: None, tmp_path: Path) -> None:
    token_file = tmp_path / "token.txt"
    token_file.write_text(TOKEN, encoding="utf-8")
    result = runner.invoke(app, [*LOGIN, "--token-file", str(token_file)])
    assert result.exit_code == 3
    assert token_file.exists()  # nothing stored, so the user's copy is not destroyed
    assert not default_config_path().exists()


def test_login_rejects_both_token_sources(memory_keyring: MemoryKeyring, tmp_path: Path) -> None:
    token_file = tmp_path / "token.txt"
    token_file.write_text(TOKEN, encoding="utf-8")
    result = runner.invoke(
        app, [*LOGIN, "--token-stdin", "--token-file", str(token_file)], input=TOKEN
    )
    assert result.exit_code == 3
    assert token_file.exists()


@pytest.mark.parametrize("content", ["", "  \n", "two words", "line1\nline2"])
def test_login_rejects_empty_or_malformed_token(
    memory_keyring: MemoryKeyring, content: str
) -> None:
    result = runner.invoke(app, [*LOGIN, "--token-stdin"], input=content)
    assert result.exit_code == 3
    assert memory_keyring.store == {}
    assert not default_config_path().exists()


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

    def factory(profile, token):  # type: ignore[no-untyped-def]
        return JiraClient(profile, token, transport=httpx.MockTransport(handler))

    monkeypatch.setattr(jira_commands, "JiraClient", factory)
    return seen


def test_search_follows_next_page_token(logged_in: MemoryKeyring, paged_jira) -> None:  # type: ignore[no-untyped-def]
    result = runner.invoke(app, ["-f", "json", "jira", "search", "project = DEMO"])
    assert result.exit_code == 0, result.output
    data = json.loads(result.stdout)
    assert [d["key"] for d in data] == ["DEMO-1", "DEMO-2", "DEMO-3", "DEMO-4", "DEMO-5"]
    assert list(data[0]) == [
        "key", "summary", "status", "status_category", "status_category_key", "issue_type",
        "priority", "assignee",
        "updated", "url",
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

    def factory(profile, token):  # type: ignore[no-untyped-def]
        return JiraClient(profile, token, transport=httpx.MockTransport(handler))

    monkeypatch.setattr(jira_commands, "JiraClient", factory)
    return seen


def test_comments_follow_start_at_pages(logged_in: MemoryKeyring, jira_with_comments) -> None:  # type: ignore[no-untyped-def]
    result = runner.invoke(app, ["-f", "json", "jira", "issue", "comments", "DEMO-123"])
    assert result.exit_code == 0, result.output
    data = json.loads(result.stdout)
    assert [c["body"] for c in data] == ["c1", "c2", "c3", "c4", "c5"]
    assert list(data[0]) == ["id", "author", "created", "updated", "visibility", "body"]
    starts = [r.url.params["startAt"] for r in jira_with_comments]
    assert starts == ["0", "2", "4"]
    assert jira_with_comments[0].url.path == "/rest/api/3/issue/DEMO-123/comment"
    assert jira_with_comments[0].url.params["orderBy"] == "created"
    assert "more exist" not in result.stderr


def test_comments_limit_and_newest_first(logged_in: MemoryKeyring, jira_with_comments) -> None:  # type: ignore[no-untyped-def]
    args = ["-f", "json", "jira", "issue", "comments", "DEMO-123", "-n", "3", "--newest-first"]
    result = runner.invoke(app, args)
    assert result.exit_code == 0, result.output
    assert len(json.loads(result.stdout)) == 3
    assert jira_with_comments[0].url.params["orderBy"] == "-created"
    assert "first 3 comments; more exist" in result.stderr


def test_comments_markdown(logged_in: MemoryKeyring, jira_with_comments) -> None:  # type: ignore[no-untyped-def]
    result = runner.invoke(app, ["-f", "markdown", "jira", "issue", "comments", "DEMO-123"])
    assert result.exit_code == 0, result.output
    assert result.stdout.startswith("## Alice Example · 2026-01-01T09:00:00.000+0100\n\nc1")


def test_issue_context_json_has_issue_and_comments(
    logged_in: MemoryKeyring,
    jira_with_comments,  # type: ignore[no-untyped-def]
) -> None:
    result = runner.invoke(app, ["-f", "json", "jira", "issue", "context", "DEMO-123"])
    assert result.exit_code == 0, result.output
    data = json.loads(result.stdout)
    assert data["key"] == "DEMO-123"
    assert data["description"] == "## Goal\n\nMake | it work"
    assert [c["body"] for c in data["comments"]] == ["c1", "c2", "c3", "c4", "c5"]
    assert list(data)[-1] == "comments"


def test_issue_context_markdown_sections(logged_in: MemoryKeyring, jira_with_comments) -> None:  # type: ignore[no-untyped-def]
    result = runner.invoke(app, ["-f", "markdown", "jira", "issue", "context", "DEMO-123"])
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
