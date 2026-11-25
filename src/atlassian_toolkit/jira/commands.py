"""``atl jira ...`` commands: parse arguments, call the service, render."""

from typing import Annotated

import typer

from atlassian_toolkit.core.client import JiraClient
from atlassian_toolkit.core.config import (
    JiraProfile,
    get_jira_profile,
    load_config,
    resolve_profile_name,
)
from atlassian_toolkit.core.context import GlobalOptions
from atlassian_toolkit.core.credentials import get_jira_token
from atlassian_toolkit.core.output import OutputFormat, emit, render_markdown, resolve_format
from atlassian_toolkit.jira import service
from atlassian_toolkit.jira.models import Issue

app = typer.Typer(help="Jira Cloud commands.", no_args_is_help=True)
issue_app = typer.Typer(help="Jira issues.", no_args_is_help=True)
app.add_typer(issue_app, name="issue")


def _open_client(options: GlobalOptions) -> tuple[JiraClient, JiraProfile]:
    """Build a client for the selected profile (profile -> token -> client)."""
    config = load_config()
    name = resolve_profile_name(options.profile, config)
    profile = get_jira_profile(name, config)
    return JiraClient(profile, get_jira_token(name)), profile


@app.command()
def me(ctx: typer.Context) -> None:
    """Show the Jira user the configured API token authenticates as."""
    options: GlobalOptions = ctx.obj
    client, _ = _open_client(options)
    with client:
        user = service.get_current_user(client)
    emit(user.to_record(), resolve_format(options.format))


@issue_app.command("get")
def issue_get(
    ctx: typer.Context,
    key: Annotated[str, typer.Argument(help="Issue key (e.g. DEMO-123) or numeric issue id.")],
) -> None:
    """Show one issue: core fields and its description converted to Markdown."""
    options: GlobalOptions = ctx.obj
    client, profile = _open_client(options)
    with client:
        issue = service.get_issue(client, key, profile.site)
    fmt = resolve_format(options.format)
    if fmt is OutputFormat.MARKDOWN:
        typer.echo(_issue_markdown(issue))
    else:
        emit(issue.to_record(), fmt)


def _issue_markdown(issue: Issue) -> str:
    """Render an issue as a Markdown document: title, metadata list, description section."""
    record = issue.to_record()
    description = record.pop("description")
    title = " ".join(f"{issue.key}: {issue.summary}".split())
    parts = [f"# {title}", render_markdown(record)]
    if description:
        parts.append(f"## Description\n\n{description}")
    return "\n\n".join(parts)
