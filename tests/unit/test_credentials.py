from collections.abc import Iterator

import keyring
import keyring.errors
import pytest
from keyring.backend import KeyringBackend

from atlassian_toolkit.core import credentials
from atlassian_toolkit.core.errors import ConfigError

SECRET = "fake-token-value"


class MemoryKeyring(KeyringBackend):
    """In-memory keyring so tests never touch the host OS keyring."""

    priority = 1  # type: ignore[assignment]

    def __init__(self) -> None:
        super().__init__()
        self.store: dict[tuple[str, str], str] = {}

    def get_password(self, service: str, username: str) -> str | None:
        return self.store.get((service, username))

    def set_password(self, service: str, username: str, password: str) -> None:
        self.store[(service, username)] = password

    def delete_password(self, service: str, username: str) -> None:
        try:
            del self.store[(service, username)]
        except KeyError:
            raise keyring.errors.PasswordDeleteError("not found") from None


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(credentials.JIRA_TOKEN_ENV_VAR, raising=False)


@pytest.fixture
def memory_keyring() -> Iterator[MemoryKeyring]:
    previous = keyring.get_keyring()
    backend = MemoryKeyring()
    keyring.set_keyring(backend)
    yield backend
    keyring.set_keyring(previous)


@pytest.fixture
def no_keyring() -> Iterator[None]:
    from keyring.backends.fail import Keyring as FailKeyring

    previous = keyring.get_keyring()
    keyring.set_keyring(FailKeyring())
    yield
    keyring.set_keyring(previous)


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


def test_missing_token_error_does_not_leak_anything(memory_keyring: MemoryKeyring) -> None:
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
