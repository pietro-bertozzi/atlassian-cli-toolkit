"""Shared fixtures: nothing here may touch the real keyring, config dir or network."""

from collections.abc import Callable, Iterator
from pathlib import Path

import httpx
import keyring
import keyring.errors
import pytest
from helpers import LOGIN, TOKEN, MemoryKeyring, route_jira, runner
from keyring.backends.fail import Keyring as FailKeyring

from atlassian_toolkit import auth_commands
from atlassian_toolkit.cli import app


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


@pytest.fixture
def logged_in(memory_keyring: MemoryKeyring) -> MemoryKeyring:
    """A ``default`` profile for example.atlassian.net with a fake token in the memory keyring."""
    result = runner.invoke(app, [*LOGIN, "--token-stdin"], input=TOKEN + "\n")
    assert result.exit_code == 0, result.output
    return memory_keyring


@pytest.fixture
def mock_jira(monkeypatch: pytest.MonkeyPatch) -> Callable[[httpx.Response], list[httpx.Request]]:
    """Answer every Jira request with the given response; returns the requests received."""

    def install(response: httpx.Response) -> list[httpx.Request]:
        seen: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            seen.append(request)
            return response

        route_jira(monkeypatch, handler)
        return seen

    return install


@pytest.fixture(autouse=True)
def _scoped_token_probe(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """Default for the post-login check in scoped mode: the token is scoped (no warning).

    Returns the sites probed; tests that need another answer patch the function again.
    """
    probed: list[str] = []

    def probe(site: str, email: str, token: str) -> bool:
        probed.append(site)
        return False

    monkeypatch.setattr(auth_commands, "token_works_on_site", probe)
    return probed
