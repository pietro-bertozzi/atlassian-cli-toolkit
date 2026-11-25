from atlassian_toolkit.core.config import normalize_site
from atlassian_toolkit.jira.models import CurrentUser


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
