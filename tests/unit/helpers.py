"""Plain helpers shared by the unit tests (fixtures live in conftest.py)."""

from collections.abc import Callable

import httpx
import keyring.errors
import pytest
from keyring.backend import KeyringBackend
from typer.testing import CliRunner

from atlassian_toolkit.core.client import JiraClient
from atlassian_toolkit.jira import connect

TOKEN = "fake-token-value"
# Deliberately untidy site URL: login must normalise it to "example.atlassian.net".
LOGIN = [
    "auth",
    "login",
    "--site",
    "https://Example.atlassian.net/",
    "--email",
    "alice@example.com",
]

runner = CliRunner()


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


def route_jira(
    monkeypatch: pytest.MonkeyPatch, handler: Callable[[httpx.Request], httpx.Response]
) -> None:
    """Make every Jira client the CLI opens answer through ``handler`` (no network)."""

    def factory(profile, token):  # type: ignore[no-untyped-def]
        return JiraClient(profile, token, transport=httpx.MockTransport(handler))

    monkeypatch.setattr(connect, "JiraClient", factory)
