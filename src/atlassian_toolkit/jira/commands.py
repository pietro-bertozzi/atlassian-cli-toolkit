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
from atlassian_toolkit.core.output import (
    OutputFormat,
    echo_err,
    emit,
    render_markdown,
    resolve_format,
)
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


SEARCH_COLUMNS = ("key", "status", "priority", "issue_type", "summary")
LimitOption = Annotated[
    int, typer.Option("--limit", "-n", min=1, max=1000, help="Maximum number of issues.")
]


@app.command()
def search(
    ctx: typer.Context,
    jql: Annotated[str, typer.Argument(help='JQL query, e.g. "project = DEMO AND status = Open".')],
    limit: LimitOption = 50,
) -> None:
    """Search issues with JQL (Jira Query Language)."""
    _run_search(ctx.obj, jql, limit)


@app.command()
def mine(ctx: typer.Context, limit: LimitOption = 50) -> None:
    """List your open issues (assigned to you, not done), most recently updated first."""
    _run_search(ctx.obj, service.MY_OPEN_ISSUES_JQL, limit)


def _run_search(options: GlobalOptions, jql: str, limit: int) -> None:
    client, profile = _open_client(options)
    with client:
        issues, more = service.search_issues(client, jql, profile.site, limit)
    emit(
        [issue.to_record() for issue in issues],
        resolve_format(options.format),
        columns=SEARCH_COLUMNS,
    )
    if more:
        echo_err(f"Showing the first {limit} issues; more match. Use --limit to see more.")


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
