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
