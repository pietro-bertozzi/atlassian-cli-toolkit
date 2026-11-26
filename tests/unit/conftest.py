"""Shared fixtures: nothing here may touch the real keyring, config dir or network."""

from collections.abc import Iterator
from pathlib import Path

import httpx
import keyring
import keyring.errors
import pytest
from keyring.backend import KeyringBackend
from keyring.backends.fail import Keyring as FailKeyring


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
def _isolated_environment(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """No inherited token/profile/config location can leak into a test."""
    monkeypatch.delenv("ATL_JIRA_API_TOKEN", raising=False)
    monkeypatch.delenv("ATL_PROFILE", raising=False)
    monkeypatch.setenv("ATL_CONFIG_DIR", str(tmp_path / "config"))


@pytest.fixture(autouse=True)
def _no_real_network(monkeypatch: pytest.MonkeyPatch) -> None:
    """Unit tests must never touch the network: fail loudly if a real HTTP request is made.

    Tests use ``httpx.MockTransport``; only the real transport is blocked.
    """

    def refuse(self, request):  # type: ignore[no-untyped-def]
        raise AssertionError(f"Unit test tried to reach the network: {request.url}")

    monkeypatch.setattr(httpx.HTTPTransport, "handle_request", refuse)


@pytest.fixture
def memory_keyring() -> Iterator[MemoryKeyring]:
    previous = keyring.get_keyring()
    backend = MemoryKeyring()
    keyring.set_keyring(backend)
    yield backend
    keyring.set_keyring(previous)


@pytest.fixture
def no_keyring() -> Iterator[None]:
    previous = keyring.get_keyring()
    keyring.set_keyring(FailKeyring())
    yield
    keyring.set_keyring(previous)
