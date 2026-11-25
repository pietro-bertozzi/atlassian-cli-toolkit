"""``atl jira ...`` commands: parse arguments, call the service, render."""

import typer

from atlassian_toolkit.core.client import JiraClient
from atlassian_toolkit.core.config import (
    get_jira_profile,
    load_config,
    resolve_profile_name,
)
from atlassian_toolkit.core.context import GlobalOptions
from atlassian_toolkit.core.credentials import get_jira_token
from atlassian_toolkit.core.output import emit, resolve_format
from atlassian_toolkit.jira import service

app = typer.Typer(help="Jira Cloud commands.", no_args_is_help=True)


def _open_client(options: GlobalOptions) -> JiraClient:
    """Build a client for the selected profile (profile -> token -> client)."""
    config = load_config()
    name = resolve_profile_name(options.profile, config)
    profile = get_jira_profile(name, config)
    return JiraClient(profile, get_jira_token(name))


@app.command()
def me(ctx: typer.Context) -> None:
    """Show the Jira user the configured API token authenticates as."""
    options: GlobalOptions = ctx.obj
    with _open_client(options) as client:
        user = service.get_current_user(client)
    emit(user.to_record(), resolve_format(options.format))
