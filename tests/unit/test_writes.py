"""Write commands: safety model (preview, dry run, confirmation) and request bodies.

Everything is mocked: no network, no real keyring, fictional data only.
"""

import json
from pathlib import Path

import httpx
import pytest
from conftest import MemoryKeyring
from typer.testing import CliRunner

from atlassian_toolkit.cli import app
from atlassian_toolkit.core.client import JiraClient
from atlassian_toolkit.jira import commands as jira_commands

TOKEN = "fake-token-value"
LOGIN = ["auth", "login", "--site", "example.atlassian.net", "--email", "alice@example.com"]
TRANSITIONS = {
    "transitions": [
        {"id": "11", "name": "Start progress", "to": {"name": "In Progress",
         "statusCategory": {"key": "indeterminate"}}, "hasScreen": False},
        {"id": "21", "name": "Send to review", "to": {"name": "In Review",
         "statusCategory": {"key": "indeterminate"}}, "hasScreen": True},
        {"id": "31", "name": "Done", "to": {"name": "Done", "statusCategory": {"key": "done"}}},
        {"id": "41", "name": "Close", "to": {"name": "Done", "statusCategory": {"key": "done"}}},
    ]
}  # fmt: skip
USERS = [
    {"accountId": "u1", "displayName": "Bob Example", "emailAddress": "bob@example.com",
     "active": True},
    {"accountId": "u2", "displayName": "Bobby Example", "active": True},
    {"accountId": "u3", "displayName": "Bob Gone", "active": False},
]  # fmt: skip

runner = CliRunner()


@pytest.fixture
def logged_in(memory_keyring: MemoryKeyring) -> MemoryKeyring:
    result = runner.invoke(app, [*LOGIN, "--token-stdin"], input=TOKEN)
    assert result.exit_code == 0, result.output
    return memory_keyring


@pytest.fixture
def jira(monkeypatch: pytest.MonkeyPatch) -> list[httpx.Request]:
    """A small fake Jira; returns the list of requests it received."""
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        path, method = request.url.path, request.method
        if path.endswith("/transitions"):
            return httpx.Response(200, json=TRANSITIONS) if method == "GET" else httpx.Response(204)
        if path.endswith("/comment") and method == "POST":
            body = {"id": "100", "created": "2026-01-10T09:00:00.000+0100"}
            return httpx.Response(201, json=body)
        if path.endswith("/assignee"):
            return httpx.Response(204)
        if path == "/rest/api/3/myself":
            return httpx.Response(200, json={"accountId": "me-1", "displayName": "Alice Example"})
        if path == "/rest/api/3/user/assignable/search":
            query = request.url.params["query"].casefold()
            matches = [u for u in USERS if u["displayName"].casefold().startswith(query)]
            return httpx.Response(200, json=matches)
        return httpx.Response(404)

    def factory(profile, token):  # type: ignore[no-untyped-def]
        return JiraClient(profile, token, transport=httpx.MockTransport(handler))

    monkeypatch.setattr(jira_commands, "JiraClient", factory)
    return seen


def writes(seen: list[httpx.Request]) -> list[httpx.Request]:
    return [r for r in seen if r.method in ("POST", "PUT")]


def body(request: httpx.Request) -> object:
    return json.loads(request.read())


# --- dry run ------------------------------------------------------------------------------


def test_dry_run_shows_the_request_and_sends_nothing(logged_in: MemoryKeyring, jira) -> None:  # type: ignore[no-untyped-def]
    args = ["-f", "json", "jira", "issue", "comment", "DEMO-1", "--body", "**hi**", "--dry-run"]
    result = runner.invoke(app, args)
    assert result.exit_code == 0, result.output
    data = json.loads(result.stdout)
    assert data["dry_run"] is True
    assert data["request"]["body"]["body"]["content"][0]["content"][0]["marks"] == [
        {"type": "strong"}
    ]
    assert "About to add this comment to DEMO-1" in result.stderr
    assert writes(jira) == []


# --- confirmation -----------------------------------------------------------------------------


def test_non_interactive_without_yes_is_refused(logged_in: MemoryKeyring, jira) -> None:  # type: ignore[no-untyped-def]
    result = runner.invoke(app, ["jira", "issue", "comment", "DEMO-1", "--body", "hi"])
    assert result.exit_code == 2
    assert "--yes" in result.stderr
    assert writes(jira) == []


def test_interactive_confirmation(
    logged_in: MemoryKeyring,
    jira,  # type: ignore[no-untyped-def]
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(jira_commands, "_is_interactive", lambda: True)
    args = ["jira", "issue", "comment", "DEMO-1", "--body", "hi"]
    refused = runner.invoke(app, args, input="n\n")
    assert refused.exit_code == 2
    assert writes(jira) == []
    accepted = runner.invoke(app, args, input="y\n")
    assert accepted.exit_code == 0, accepted.output
    assert len(writes(jira)) == 1


# --- comment ----------------------------------------------------------------------------------


def test_comment_with_yes_sends_one_adf_post(logged_in: MemoryKeyring, jira) -> None:  # type: ignore[no-untyped-def]
    args = ["-f", "json", "jira", "issue", "comment", "DEMO-1", "--body", "Done in `main`", "-y"]
    result = runner.invoke(app, args)
    assert result.exit_code == 0, result.output
    assert json.loads(result.stdout) == {
        "key": "DEMO-1",
        "dry_run": False,
        "comment_id": "100",
        "created": "2026-01-10T09:00:00.000+0100",
    }
    [post] = writes(jira)
    assert post.url.path == "/rest/api/3/issue/DEMO-1/comment"
    assert body(post) == {
        "body": {
            "type": "doc",
            "version": 1,
            "content": [
                {
                    "type": "paragraph",
                    "content": [
                        {"type": "text", "text": "Done in "},
                        {"type": "text", "text": "main", "marks": [{"type": "code"}]},
                    ],
                }
            ],
        }
    }


def test_comment_from_file_and_stdin(logged_in: MemoryKeyring, jira, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    note = tmp_path / "note.md"
    note.write_text("from a file", encoding="utf-8")
    base = ["jira", "issue", "comment", "DEMO-1", "-y"]
    assert runner.invoke(app, [*base, "--body-file", str(note)]).exit_code == 0
    assert runner.invoke(app, [*base, "--body-file", "-"], input="from stdin").exit_code == 0
    texts = [body(r)["body"]["content"][0]["content"][0]["text"] for r in writes(jira)]  # type: ignore[index]
    assert texts == ["from a file", "from stdin"]


@pytest.mark.parametrize(
    "extra",
    [[], ["--body", "  "], ["--body", "a", "--body-file", "-"]],
)
def test_comment_body_errors(logged_in: MemoryKeyring, jira, extra: list[str]) -> None:  # type: ignore[no-untyped-def]
    result = runner.invoke(app, ["jira", "issue", "comment", "DEMO-1", "-y", *extra])
    assert result.exit_code == 2
    assert writes(jira) == []


# --- transitions ------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("target", "expected_id"),
    [("start progress", "11"), ("In Review", "21"), ("close", "41")],
)
def test_transition_by_name_or_status(
    logged_in: MemoryKeyring,
    jira,  # type: ignore[no-untyped-def]
    target: str,
    expected_id: str,
) -> None:
    args = ["-f", "json", "jira", "issue", "transition", "DEMO-1", "--to", target, "-y"]
    result = runner.invoke(app, args)
    assert result.exit_code == 0, result.output
    [post] = writes(jira)
    assert body(post) == {"transition": {"id": expected_id}}
    assert json.loads(result.stdout)["transition_id"] == expected_id


def test_transition_screen_warning(logged_in: MemoryKeyring, jira) -> None:  # type: ignore[no-untyped-def]
    result = runner.invoke(
        app, ["jira", "issue", "transition", "DEMO-1", "--to", "In Review", "-y"]
    )
    assert "has a screen" in result.stderr


@pytest.mark.parametrize("target", ["Nowhere", "done-ish"])
def test_transition_no_match_lists_options(logged_in: MemoryKeyring, jira, target: str) -> None:  # type: ignore[no-untyped-def]
    result = runner.invoke(app, ["jira", "issue", "transition", "DEMO-1", "--to", target, "-y"])
    assert result.exit_code == 2
    assert "Send to review" in result.stderr
    assert writes(jira) == []


def test_transition_status_reached_by_two_names_is_ambiguous_unless_named(
    logged_in: MemoryKeyring,
    jira,  # type: ignore[no-untyped-def]
) -> None:
    # "Done" is both a transition name and a status reached by two transitions:
    # the transition name wins, so it is not ambiguous.
    result = runner.invoke(app, ["-f", "json", "jira", "issue", "transition", "DEMO-1",
                                 "--to", "done", "-y"])  # fmt: skip
    assert result.exit_code == 0, result.output
    assert body(writes(jira)[0]) == {"transition": {"id": "31"}}


# --- assign -----------------------------------------------------------------------------------


def test_assign_to_me(logged_in: MemoryKeyring, jira) -> None:  # type: ignore[no-untyped-def]
    result = runner.invoke(app, ["-f", "json", "jira", "issue", "assign", "DEMO-1", "--to", "me",
                                 "-y"])  # fmt: skip
    assert result.exit_code == 0, result.output
    [put] = writes(jira)
    assert put.url.path == "/rest/api/3/issue/DEMO-1/assignee"
    assert body(put) == {"accountId": "me-1"}
    assert json.loads(result.stdout)["assignee"] == "Alice Example"


def test_assign_exact_name_wins_over_prefix_matches(logged_in: MemoryKeyring, jira) -> None:  # type: ignore[no-untyped-def]
    args = ["jira", "issue", "assign", "DEMO-1", "--to", "bob example", "-y"]
    result = runner.invoke(app, args)
    assert result.exit_code == 0, result.output
    assert body(writes(jira)[0]) == {"accountId": "u1"}


def test_assign_ambiguous_lists_candidates(logged_in: MemoryKeyring, jira) -> None:  # type: ignore[no-untyped-def]
    result = runner.invoke(app, ["jira", "issue", "assign", "DEMO-1", "--to", "bob", "-y"])
    assert result.exit_code == 2
    assert "Bob Example (u1)" in result.stderr
    assert "Bob Gone" not in result.stderr  # inactive users are not candidates
    assert writes(jira) == []


def test_assign_unassign_and_account_id(logged_in: MemoryKeyring, jira) -> None:  # type: ignore[no-untyped-def]
    base = ["jira", "issue", "assign", "DEMO-1", "-y"]
    assert runner.invoke(app, [*base, "--unassign"]).exit_code == 0
    assert runner.invoke(app, [*base, "--account-id", "u9"]).exit_code == 0
    assert [body(r) for r in writes(jira)] == [{"accountId": None}, {"accountId": "u9"}]


@pytest.mark.parametrize("extra", [[], ["--to", "me", "--unassign"]])
def test_assign_needs_exactly_one_target(logged_in: MemoryKeyring, jira, extra: list[str]) -> None:  # type: ignore[no-untyped-def]
    result = runner.invoke(app, ["jira", "issue", "assign", "DEMO-1", "-y", *extra])
    assert result.exit_code == 2
    assert writes(jira) == []


@pytest.mark.parametrize(
    "args",
    [
        ["transition", "DEMO-1", "--to", "In Review"],
        ["assign", "DEMO-1", "--to", "me"],
        ["assign", "DEMO-1", "--unassign"],
        ["comment", "DEMO-1", "--body", "hi"],
    ],
)
def test_dry_run_never_sends_a_write(  # type: ignore[no-untyped-def]
    logged_in: MemoryKeyring, jira, args: list[str]
) -> None:
    result = runner.invoke(app, ["-f", "json", "jira", "issue", *args, "--dry-run", "--yes"])
    assert result.exit_code == 0, result.output
    assert json.loads(result.stdout)["dry_run"] is True
    assert writes(jira) == []
    assert "Dry run: nothing was sent." in result.stderr
