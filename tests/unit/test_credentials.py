import pytest
from conftest import MemoryKeyring

from atlassian_toolkit.core import credentials
from atlassian_toolkit.core.errors import ConfigError

SECRET = "fake-token-value"


def test_save_and_get_roundtrip(memory_keyring: MemoryKeyring) -> None:
    credentials.save_jira_token("work", SECRET)
    assert credentials.get_jira_token("work") == SECRET
    assert memory_keyring.store == {("atl-jira", "work"): SECRET}


def test_tokens_are_per_profile(memory_keyring: MemoryKeyring) -> None:
    credentials.save_jira_token("a", "token-a")
    assert not credentials.has_jira_token("b")


def test_env_var_used_when_keyring_empty(
    memory_keyring: MemoryKeyring, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(credentials.JIRA_TOKEN_ENV_VAR, SECRET)
    assert credentials.get_jira_token("work") == SECRET


def test_env_wins_over_keyring(
    memory_keyring: MemoryKeyring, monkeypatch: pytest.MonkeyPatch
) -> None:
    credentials.save_jira_token("work", "from-keyring")
    monkeypatch.setenv(credentials.JIRA_TOKEN_ENV_VAR, "from-env")
    assert credentials.get_jira_token("work") == "from-env"


def test_token_source(memory_keyring: MemoryKeyring, monkeypatch: pytest.MonkeyPatch) -> None:
    assert credentials.jira_token_source("work") is None
    credentials.save_jira_token("work", SECRET)
    assert credentials.jira_token_source("work") == "keyring"
    monkeypatch.setenv(credentials.JIRA_TOKEN_ENV_VAR, "x")
    assert credentials.jira_token_source("work") == "environment"


def test_missing_token_error_points_to_login(memory_keyring: MemoryKeyring) -> None:
    with pytest.raises(ConfigError, match="atl auth login"):
        credentials.get_jira_token("work")


def test_no_backend_falls_back_to_env(no_keyring: None, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(credentials.JIRA_TOKEN_ENV_VAR, SECRET)
    assert credentials.get_jira_token("work") == SECRET


def test_no_backend_and_no_env_is_config_error(no_keyring: None) -> None:
    with pytest.raises(ConfigError):
        credentials.get_jira_token("work")


def test_save_without_backend_points_to_env_var(no_keyring: None) -> None:
    with pytest.raises(ConfigError, match=credentials.JIRA_TOKEN_ENV_VAR):
        credentials.save_jira_token("work", SECRET)


def test_save_rejects_empty_token(memory_keyring: MemoryKeyring) -> None:
    with pytest.raises(ConfigError):
        credentials.save_jira_token("work", "")


def test_delete(memory_keyring: MemoryKeyring) -> None:
    credentials.save_jira_token("work", SECRET)
    assert credentials.delete_jira_token("work") is True
    assert credentials.delete_jira_token("work") is False
