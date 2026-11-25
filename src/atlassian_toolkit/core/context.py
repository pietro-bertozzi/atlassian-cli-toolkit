"""Global CLI options shared by every command (``--profile``, ``--format``, ``--verbose``)."""

from __future__ import annotations

from dataclasses import dataclass

from atlassian_toolkit.core.output import OutputFormat


@dataclass(frozen=True)
class GlobalOptions:
    """Values of the root-level options, stored in the Typer context for sub-commands."""

    profile: str | None = None
    format: OutputFormat | None = None
    verbose: bool = False
