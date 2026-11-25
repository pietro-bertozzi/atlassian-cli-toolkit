"""API token storage: ``ATL_JIRA_API_TOKEN`` overrides the OS keyring (headless/CI use).

Tokens are never written to files, never logged and never included in error messages.
"""

from __future__ import annotations

import os

import keyring
from keyring.errors import KeyringError, NoKeyringError

from atlassian_toolkit.core.errors import ConfigError

JIRA_SERVICE = "atl-jira"
JIRA_TOKEN_ENV_VAR = "ATL_JIRA_API_TOKEN"

_NO_BACKEND_HINT = (
    f"No usable OS keyring is available. Set the {JIRA_TOKEN_ENV_VAR} environment variable "
    "instead (headless/CI use)."
)


def get_jira_token(profile: str) -> str:
    """Return the Jira API token for ``profile``.

    ``ATL_JIRA_API_TOKEN``, when set, takes precedence over the OS keyring.

    Raises:
        ConfigError: if no token can be found.
    """
    token = os.environ.get(JIRA_TOKEN_ENV_VAR) or _read_keyring(profile)
    if token:
        return token
    raise ConfigError(
        f"No API token found for profile {profile!r}. "
        f"Run 'atl auth login' or set {JIRA_TOKEN_ENV_VAR}."
    )


def has_jira_token(profile: str) -> bool:
    """Return whether a token is available for ``profile`` (without exposing it)."""
    try:
        get_jira_token(profile)
    except ConfigError:
        return False
    return True


def save_jira_token(profile: str, token: str) -> None:
    """Store the token for ``profile`` in the OS keyring."""
    if not token:
        raise ConfigError("Refusing to store an empty API token.")
    try:
        keyring.set_password(JIRA_SERVICE, profile, token)
    except NoKeyringError as exc:
        raise ConfigError(_NO_BACKEND_HINT) from exc
    except KeyringError as exc:
        raise ConfigError(f"Could not store the token in the OS keyring: {_describe(exc)}") from exc


def delete_jira_token(profile: str) -> bool:
    """Remove the token for ``profile`` from the keyring. Return whether one was removed."""
    try:
        keyring.delete_password(JIRA_SERVICE, profile)
    except keyring.errors.PasswordDeleteError:
        return False
    except NoKeyringError as exc:
        raise ConfigError(_NO_BACKEND_HINT) from exc
    except KeyringError as exc:
        raise ConfigError(
            f"Could not delete the token from the OS keyring: {_describe(exc)}"
        ) from exc
    return True


def _read_keyring(profile: str) -> str | None:
    """Read from the keyring; a missing backend is not an error (it just means no token)."""
    try:
        return keyring.get_password(JIRA_SERVICE, profile)
    except NoKeyringError:
        return None
    except KeyringError as exc:
        raise ConfigError(f"Could not read the OS keyring: {_describe(exc)}") from exc


def _describe(exc: Exception) -> str:
    """Describe a keyring error by type only, in case the message carries sensitive data."""
    return type(exc).__name__
