from atlassian_toolkit.core.config import normalize_site
from atlassian_toolkit.jira.models import Comment, CurrentUser, Issue


def test_from_api_maps_fields() -> None:
    user = CurrentUser.from_api(
        {
            "accountId": "abc123",
            "displayName": "Alice Example",
            "emailAddress": "alice@example.com",
            "active": True,
            "timeZone": "Europe/Rome",
            "accountType": "atlassian",
            "self": "https://example.atlassian.net/rest/api/3/user?accountId=abc123",
        }
    )
    assert user.account_id == "abc123"
    assert user.to_record()["display_name"] == "Alice Example"
    assert "self" not in user.to_record()


def test_from_api_handles_null_privacy_fields() -> None:
    user = CurrentUser.from_api(
        {"accountId": "abc123", "displayName": "A", "emailAddress": None, "timeZone": None}
    )
    assert user.email is None
    assert user.time_zone is None
    assert user.active is False


def test_normalize_site() -> None:
    assert normalize_site("https://Example.atlassian.net/") == "example.atlassian.net"
    assert normalize_site(" example.atlassian.net ") == "example.atlassian.net"
    assert normalize_site("http://example.atlassian.net/jira/x") == "example.atlassian.net"


ISSUE_BODY = {
    "id": "10001",
    "key": "DEMO-123",
    "self": "https://example.atlassian.net/rest/api/3/issue/10001",
    "fields": {
        "summary": "Fix the login page",
        "issuetype": {"name": "Bug"},
        "status": {
            "name": "In Progress",
            "statusCategory": {"key": "indeterminate", "name": "In Progress"},
        },
        "priority": {"name": "High"},
        "project": {"key": "DEMO", "name": "Demo project"},
        "parent": {"key": "DEMO-100"},
        "assignee": {"accountId": "abc123", "displayName": "Alice Example"},
        "reporter": {"accountId": "def456", "displayName": "Bob Example"},
        "labels": ["frontend", "login"],
        "resolution": None,
        "created": "2026-01-10T09:00:00.000+0100",
        "updated": "2026-01-11T10:30:00.000+0100",
        "duedate": "2026-02-01",
        "subtasks": [
            {
                "id": "10010",
                "key": "DEMO-124",
                "fields": {
                    "summary": "Write the fix",
                    "status": {"name": "Done", "statusCategory": {"key": "done"}},
                    "issuetype": {"name": "Sub-task"},
                },
            }
        ],
        "issuelinks": [
            {
                "id": "1",
                "type": {"name": "Blocks", "inward": "is blocked by", "outward": "blocks"},
                "outwardIssue": {"key": "DEMO-7", "fields": {"summary": "Release"}},
            },
            {
                "id": "2",
                "type": {"name": "Blocks", "inward": "is blocked by", "outward": "blocks"},
                "inwardIssue": {"key": "DEMO-9", "fields": {"summary": "Login API"}},
            },
            {"id": "3", "type": {"name": "Broken"}},
        ],
        "description": {
            "type": "doc",
            "version": 1,
            "content": [
                {"type": "paragraph", "content": [{"type": "text", "text": "Steps:"}]},
                {
                    "type": "bulletList",
                    "content": [
                        {
                            "type": "listItem",
                            "content": [
                                {"type": "paragraph", "content": [{"type": "text", "text": "Open"}]}
                            ],
                        }
                    ],
                },
            ],
        },
    },
}


def test_issue_from_api_maps_fields() -> None:
    issue = Issue.from_api(ISSUE_BODY, "example.atlassian.net")
    assert issue.to_record() == {
        "key": "DEMO-123",
        "id": "10001",
        "url": "https://example.atlassian.net/browse/DEMO-123",
        "summary": "Fix the login page",
        "issue_type": "Bug",
        "status": "In Progress",
        "status_category": "In Progress",
        "status_category_key": "indeterminate",
        "priority": "High",
        "project_key": "DEMO",
        "parent_key": "DEMO-100",
        "assignee": "Alice Example",
        "reporter": "Bob Example",
        "labels": ["frontend", "login"],
        "resolution": None,
        "created": "2026-01-10T09:00:00.000+0100",
        "updated": "2026-01-11T10:30:00.000+0100",
        "due_date": "2026-02-01",
        "subtasks": [
            {
                "key": "DEMO-124",
                "summary": "Write the fix",
                "status": "Done",
                "status_category_key": "done",
                "issue_type": "Sub-task",
            }
        ],
        "links": [
            {
                "key": "DEMO-7",
                "summary": "Release",
                "status": None,
                "status_category_key": None,
                "issue_type": None,
                "relation": "blocks",
            },
            {
                "key": "DEMO-9",
                "summary": "Login API",
                "status": None,
                "status_category_key": None,
                "issue_type": None,
                "relation": "is blocked by",
            },
        ],
        "description": "Steps:\n\n- Open",
    }


def test_issue_from_api_handles_missing_and_null_fields() -> None:
    issue = Issue.from_api(
        {
            "id": "10002",
            "key": "DEMO-2",
            "fields": {"summary": "S", "assignee": None, "labels": None},
        },
        "example.atlassian.net",
    )
    record = issue.to_record()
    assert record["assignee"] is None
    assert record["priority"] is None
    assert record["status_category"] is None
    assert record["labels"] == []
    assert record["description"] is None


def test_issue_from_api_tolerates_missing_fields_object() -> None:
    issue = Issue.from_api({"key": "DEMO-3"}, "example.atlassian.net")
    assert issue.summary == ""
    assert issue.id == ""


def test_comment_from_api() -> None:
    comment = Comment.from_api(
        {
            "id": "100",
            "author": {"accountId": "abc123", "displayName": "Alice Example"},
            "body": {
                "type": "doc",
                "version": 1,
                "content": [{"type": "paragraph", "content": [{"type": "text", "text": "LGTM"}]}],
            },
            "created": "2026-01-10T09:00:00.000+0100",
            "updated": "2026-01-10T09:05:00.000+0100",
            "visibility": {"type": "role", "value": "Developers"},
        }
    )
    assert comment.to_record() == {
        "id": "100",
        "author": "Alice Example",
        "created": "2026-01-10T09:00:00.000+0100",
        "updated": "2026-01-10T09:05:00.000+0100",
        "visibility": "Developers",
        "body": "LGTM",
    }


def test_comment_from_api_tolerates_missing_fields() -> None:
    comment = Comment.from_api({"id": "101"})
    assert comment.author is None
    assert comment.visibility is None
    assert comment.body == ""
