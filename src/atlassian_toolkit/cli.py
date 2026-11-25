"""Root Typer app: global options and wiring of the sub-apps. No business logic."""

import logging
import sys
from typing import Annotated

import typer
from typer.core import TyperGroup

from atlassian_toolkit import __version__, auth_commands
from atlassian_toolkit.core.context import GlobalOptions
from atlassian_toolkit.core.errors import AtlError
from atlassian_toolkit.core.output import OutputFormat, configure_stdio, echo_err
from atlassian_toolkit.jira import commands as jira_commands


class AtlGroup(TyperGroup):
    """Root group that turns expected errors into a stderr message and a specific exit code."""

    def invoke(self, ctx):  # type: ignore[no-untyped-def]
        try:
            return super().invoke(ctx)
        except AtlError as exc:
            echo_err(f"Error: {exc}")
            ctx.exit(exc.exit_code)


# pretty_exceptions_show_locals=False: a traceback must never print local variables (tokens).
app = typer.Typer(
    name="atl",
    cls=AtlGroup,
    help="Read-only CLI for Atlassian Cloud.",
    no_args_is_help=True,
    add_completion=False,
    pretty_exceptions_show_locals=False,
)
app.add_typer(auth_commands.app, name="auth")
app.add_typer(jira_commands.app, name="jira")


def _version_callback(value: bool) -> None:
    if value:
        typer.echo(f"atl {__version__}")
        raise typer.Exit()


def _setup_logging(verbose: bool) -> None:
    """Send our own logs to stderr; DEBUG with --verbose, otherwise warnings only."""
    logger = logging.getLogger("atl")
    logger.handlers.clear()
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(logging.Formatter("%(message)s"))
    logger.addHandler(handler)
    logger.setLevel(logging.DEBUG if verbose else logging.WARNING)
    logger.propagate = False


@app.callback()
def main(
    ctx: typer.Context,
    profile: Annotated[
        str | None,
        typer.Option("--profile", "-p", help="Profile to use (default: ATL_PROFILE or config)."),
    ] = None,
    format: Annotated[
        OutputFormat | None,
        typer.Option("--format", "-f", help="Output format (default: table on a TTY, else json)."),
    ] = None,
    verbose: Annotated[
        bool, typer.Option("--verbose", "-v", help="Log requests to stderr (never credentials).")
    ] = False,
    version: Annotated[
        bool,
        typer.Option("--version", callback=_version_callback, is_eager=True, help="Show version."),
    ] = False,
) -> None:
    """Global options shared by all commands."""
    configure_stdio()
    _setup_logging(verbose)
    ctx.obj = GlobalOptions(profile=profile, format=format, verbose=verbose)
