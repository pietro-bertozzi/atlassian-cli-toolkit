"""``atl auth ...``: login, status (and --check), logout. Keyring and HTTP mocked."""

import base64
import json
from pathlib import Path

import httpx
import pytest
from helpers import LOGIN, TOKEN, MemoryKeyring, runner

from atlassian_toolkit import auth_commands
from atlassian_toolkit.cli import app
from atlassian_toolkit.core.config import default_config_path
from atlassian_toolkit.core.errors import ConfigError

ME_BODY = {
    "accountId": "abc123",
    "displayName": "Alice Example",
    "emailAddress": "alice@example.com",
    "active": True,
    "timeZone": "Europe/Rome",
    "accountType": "atlassian",
}


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


CLOUD_ID = "11111111-2222-3333-4444-555555555555"


def test_login_scoped_discovers_cloud_id(
    memory_keyring: MemoryKeyring, monkeypatch: pytest.MonkeyPatch
) -> None:
    asked: list[str] = []
    monkeypatch.setattr(
        auth_commands, "discover_cloud_id", lambda site: asked.append(site) or CLOUD_ID
    )
    result = runner.invoke(app, [*LOGIN, "--mode", "scoped", "--token-stdin"], input=TOKEN)
    assert result.exit_code == 0, result.output
    assert asked == ["example.atlassian.net"]
    assert f'cloud_id = "{CLOUD_ID}"' in default_config_path().read_text()


def test_login_scoped_discovery_failure_saves_nothing(
    memory_keyring: MemoryKeyring, monkeypatch: pytest.MonkeyPatch
) -> None:
    def fail(site: str) -> str:
        raise ConfigError("Could not find the Cloud ID. Pass it with --cloud-id")

    monkeypatch.setattr(auth_commands, "discover_cloud_id", fail)
    result = runner.invoke(app, [*LOGIN, "--mode", "scoped", "--token-stdin"], input=TOKEN)
    assert result.exit_code == 3
    assert "--cloud-id" in result.stderr
    assert memory_keyring.store == {}
    assert not default_config_path().exists()


def test_login_scoped_explicit_cloud_id_skips_discovery(
    memory_keyring: MemoryKeyring, monkeypatch: pytest.MonkeyPatch
) -> None:
    def boom(site: str) -> str:
        raise AssertionError("must not be called")

    monkeypatch.setattr(auth_commands, "discover_cloud_id", boom)
    args = [*LOGIN, "--mode", "scoped", "--cloud-id", CLOUD_ID, "--token-stdin"]
    assert runner.invoke(app, args, input=TOKEN).exit_code == 0


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


def test_status_check_asks_jira_who_i_am(logged_in: MemoryKeyring, mock_jira) -> None:  # type: ignore[no-untyped-def]
    seen = mock_jira(httpx.Response(200, json=ME_BODY))
    result = runner.invoke(app, ["-f", "json", "auth", "status", "--check"])
    assert result.exit_code == 0, result.output
    data = json.loads(result.stdout)
    assert (data["check"], data["account_id"], data["display_name"]) == (
        "ok",
        "abc123",
        "Alice Example",
    )
    assert str(seen[0].url) == "https://example.atlassian.net/rest/api/3/myself"
    assert TOKEN not in result.output


def test_status_without_check_makes_no_request(logged_in: MemoryKeyring, mock_jira) -> None:  # type: ignore[no-untyped-def]
    seen = mock_jira(httpx.Response(200, json=ME_BODY))
    data = json.loads(runner.invoke(app, ["-f", "json", "auth", "status"]).stdout)
    assert "check" not in data
    assert seen == []


def test_status_check_401_exits_4_with_message_on_stderr(
    logged_in: MemoryKeyring, mock_jira
) -> None:  # type: ignore[no-untyped-def]
    mock_jira(httpx.Response(401))
    result = runner.invoke(app, ["auth", "status", "--check"])
    assert result.exit_code == 4
    assert "expired or revoked" in result.stderr
    assert result.stdout == ""
    assert TOKEN not in result.output


def test_jira_me_command_is_gone(logged_in: MemoryKeyring) -> None:
    assert runner.invoke(app, ["jira", "me"]).exit_code == 2


def test_status_check_uses_env_token_over_keyring(
    logged_in: MemoryKeyring,
    mock_jira,
    monkeypatch: pytest.MonkeyPatch,  # type: ignore[no-untyped-def]
) -> None:
    seen = mock_jira(httpx.Response(200, json=ME_BODY))
    monkeypatch.setenv("ATL_JIRA_API_TOKEN", "env-token")
    runner.invoke(app, ["auth", "status", "--check"])
    assert base64.b64decode(seen[0].headers["Authorization"].split()[1]) == (
        b"alice@example.com:env-token"
    )


def test_config_dir_override_is_used(tmp_path: Path, logged_in: MemoryKeyring) -> None:
    assert default_config_path() == tmp_path / "config" / "config.toml"


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


# --- login safety nets ------------------------------------------------------------------------


def test_login_warns_before_replacing_an_existing_profile(logged_in: MemoryKeyring) -> None:
    result = runner.invoke(app, [*LOGIN, "--token-stdin"], input="other-token")
    assert result.exit_code == 0, result.output
    assert "profile 'default' already exists; it will be replaced" in result.stderr
    assert logged_in.store == {("atl-jira", "default"): "other-token"}


def test_login_new_profile_has_no_replace_note(memory_keyring: MemoryKeyring) -> None:
    result = runner.invoke(app, [*LOGIN, "--token-stdin"], input=TOKEN)
    assert "already exists" not in result.stderr


@pytest.mark.parametrize("content", [TOKEN + "12:34", "tok@en", "tokenè"])
def test_login_rejects_token_with_foreign_characters(
    memory_keyring: MemoryKeyring, content: str
) -> None:
    result = runner.invoke(app, [*LOGIN, "--token-stdin"], input=content)
    assert result.exit_code == 3
    assert "Copy only the token" in result.stderr
    assert content not in result.output  # never echo the (bad) token back
    assert memory_keyring.store == {}
    assert not default_config_path().exists()


def test_login_accepts_base64_style_tokens(memory_keyring: MemoryKeyring) -> None:
    token = "ATATT3xFf-_GF0+abc/def.ghi=0A1B2C3D"
    assert runner.invoke(app, [*LOGIN, "--token-stdin"], input=token).exit_code == 0


def test_scoped_login_warns_when_the_token_is_classic(
    memory_keyring: MemoryKeyring, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(auth_commands, "token_works_on_site", lambda site, email, token: True)
    args = [*LOGIN, "--mode", "scoped", "--cloud-id", CLOUD_ID, "--token-stdin"]
    result = runner.invoke(app, args, input=TOKEN)
    assert result.exit_code == 0, result.output  # saved anyway: it is a warning
    assert "it is a classic (unscoped) API token" in result.stderr
    assert TOKEN not in result.output


def test_scoped_login_with_scoped_token_has_no_warning(
    memory_keyring: MemoryKeyring, _scoped_token_probe: list[str]
) -> None:
    args = [*LOGIN, "--mode", "scoped", "--cloud-id", CLOUD_ID, "--token-stdin"]
    result = runner.invoke(app, args, input=TOKEN)
    assert result.exit_code == 0, result.output
    assert _scoped_token_probe == ["example.atlassian.net"]
    assert "Warning" not in result.stderr


def test_classic_login_does_not_probe(
    memory_keyring: MemoryKeyring, _scoped_token_probe: list[str]
) -> None:
    assert runner.invoke(app, [*LOGIN, "--token-stdin"], input=TOKEN).exit_code == 0
    assert _scoped_token_probe == []


def test_scope_mismatch_401_says_which_scope_is_missing(
    logged_in: MemoryKeyring, mock_jira
) -> None:  # type: ignore[no-untyped-def]
    body = {"code": 401, "message": "Unauthorized; scope does not match"}
    mock_jira(httpx.Response(401, json=body))
    result = runner.invoke(app, ["auth", "status", "--check"])
    assert result.exit_code == 4
    assert "scope does not match" in result.stderr
    assert "write:jira-work" in result.stderr
    assert "expired or revoked" not in result.stderr
