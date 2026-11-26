"""Exception hierarchy. Each exception carries the process exit code the CLI should use.

The root command group (``cli.py``) prints ``Error: <message>`` to stderr and exits with
``exit_code``.
"""

from __future__ import annotations


class AtlError(Exception):
    """Base class for all expected, user-facing errors."""

    exit_code = 1


class ConfigError(AtlError):
    """Missing, invalid or inconsistent configuration (including missing credentials)."""

    exit_code = 3


class AuthError(AtlError):
    """Authentication or authorisation failure (HTTP 401 / 403)."""

    exit_code = 4


class NotFoundError(AtlError):
    """The requested resource does not exist or is not visible (HTTP 404)."""

    exit_code = 5


class ApiError(AtlError):
    """Unexpected API response or network failure."""

    exit_code = 6


class UsageError(AtlError):
    """The command cannot run as given (ambiguous target, missing confirmation...)."""

    exit_code = 2
