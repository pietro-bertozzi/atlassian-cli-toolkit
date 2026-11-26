"""``atl jira ...`` commands: parse arguments, call the service, render."""

from collections.abc import Mapping
from typing import Annotated, Any

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
    """Show one issue: core fields, subtasks, links and the description as Markdown."""
    options: GlobalOptions = ctx.obj
    client, profile = _open_client(options)
    with client:
        issue = service.get_issue(client, key, profile.site)
    fmt = resolve_format(options.format)
    if fmt is OutputFormat.MARKDOWN:
        typer.echo(_issue_markdown(issue))
    elif fmt is OutputFormat.TABLE:
        emit(_table_record(issue.to_record()), fmt)
    else:
        emit(issue.to_record(), fmt)


CommentsLimitOption = Annotated[
    int, typer.Option("--limit", "-n", min=1, max=1000, help="Maximum number of comments.")
]
NewestFirstOption = Annotated[
    bool, typer.Option("--newest-first", help="Newest comments first (default: oldest first).")
]
COMMENT_COLUMNS = ("created", "author", "body")


@issue_app.command("comments")
def issue_comments(
    ctx: typer.Context,
    key: Annotated[str, typer.Argument(help="Issue key (e.g. DEMO-123) or numeric issue id.")],
    limit: CommentsLimitOption = 100,
    newest_first: NewestFirstOption = False,
) -> None:
    """Show an issue's comments, converted to Markdown (oldest first)."""
    options: GlobalOptions = ctx.obj
    client, _ = _open_client(options)
    with client:
        comments, more = service.get_comments(client, key, limit, newest_first)
    fmt = resolve_format(options.format)
    if fmt is OutputFormat.MARKDOWN:
        typer.echo(_comments_markdown([c.to_record() for c in comments], heading_level=2))
    else:
        emit([c.to_record() for c in comments], fmt, columns=COMMENT_COLUMNS)
    _warn_more_comments(more, limit)


@issue_app.command("context")
def issue_context(
    ctx: typer.Context,
    key: Annotated[str, typer.Argument(help="Issue key (e.g. DEMO-123) or numeric issue id.")],
    limit: CommentsLimitOption = 100,
) -> None:
    """Everything needed to understand an issue in one call: fields, subtasks, links,
    description and comments. Meant for coding agents (use -f json or -f markdown)."""
    options: GlobalOptions = ctx.obj
    client, profile = _open_client(options)
    with client:
        issue = service.get_issue(client, key, profile.site)
        comments, more = service.get_comments(client, issue.key or key, limit)
    comment_records = [c.to_record() for c in comments]
    fmt = resolve_format(options.format)
    if fmt is OutputFormat.MARKDOWN:
        typer.echo(_issue_markdown(issue, comment_records))
    elif fmt is OutputFormat.TABLE:
        emit(_table_record(issue.to_record()), fmt)
        emit(comment_records, fmt, columns=COMMENT_COLUMNS)
    else:
        emit({**issue.to_record(), "comments": comment_records}, fmt)
    _warn_more_comments(more, limit)


def _warn_more_comments(more: bool, limit: int) -> None:
    if more:
        echo_err(f"Showing the first {limit} comments; more exist. Use --limit to see more.")


def _ref_line(ref: Mapping[str, Any]) -> str:
    """One line for a related issue: ``KEY [status] summary``."""
    status = f" [{ref['status']}]" if ref.get("status") else ""
    return " ".join(f"{ref['key']}{status} {ref['summary']}".split())


def _table_record(record: dict[str, Any]) -> dict[str, Any]:
    """Make subtasks/links readable in a table: one ``KEY [status] summary`` line each."""
    display = dict(record)
    display["subtasks"] = "\n".join(_ref_line(s) for s in record["subtasks"])
    display["links"] = "\n".join(f"{x['relation']} {_ref_line(x)}" for x in record["links"])
    return display


def _issue_markdown(issue: Issue, comments: list[dict[str, Any]] | None = None) -> str:
    """Render an issue as a Markdown document.

    Sections: title, metadata list, description, subtasks, links and (when given) comments.
    """
    record = issue.to_record()
    description = record.pop("description")
    subtasks = record.pop("subtasks")
    links = record.pop("links")
    title = " ".join(f"{issue.key}: {issue.summary}".split())
    parts = [f"# {title}", render_markdown(record)]
    if description:
        parts.append(f"## Description\n\n{description}")
    if subtasks:
        parts.append("## Subtasks\n\n" + "\n".join(f"- {_ref_line(s)}" for s in subtasks))
    if links:
        lines = (f"- {x['relation']} {_ref_line(x)}" for x in links)
        parts.append("## Links\n\n" + "\n".join(lines))
    if comments is not None:
        parts.append("## Comments\n\n" + _comments_markdown(comments, heading_level=3))
    return "\n\n".join(parts)


def _comments_markdown(comments: list[dict[str, Any]], heading_level: int) -> str:
    """Render comments as Markdown: one heading per comment (author · date), then its body."""
    if not comments:
        return "_No comments._"
    hashes = "#" * heading_level
    blocks = []
    for comment in comments:
        meta = [comment["author"] or "Unknown author", comment["created"] or ""]
        if comment["updated"] and comment["updated"] != comment["created"]:
            meta.append(f"edited {comment['updated']}")
        if comment["visibility"]:
            meta.append(f"visible to {comment['visibility']}")
        heading = " ".join(" · ".join(part for part in meta if part).split())
        blocks.append(f"{hashes} {heading}\n\n{comment['body'] or '_(empty)_'}")
    return "\n\n".join(blocks)


PROJECT_COLUMNS = ("key", "name", "project_type", "style")
FIELD_COLUMNS = ("id", "name", "type", "custom")


@app.command()
def projects(
    ctx: typer.Context,
    query: Annotated[
        str | None,
        typer.Option("--query", "-q", help="Only projects whose key or name contains this."),
    ] = None,
    limit: Annotated[
        int, typer.Option("--limit", "-n", min=1, max=1000, help="Maximum number of projects.")
    ] = 200,
) -> None:
    """List the projects you can view (key, name, type, company/team-managed)."""
    options: GlobalOptions = ctx.obj
    client, profile = _open_client(options)
    with client:
        found, more = service.list_projects(client, profile.site, query, limit)
    emit([p.to_record() for p in found], resolve_format(options.format), columns=PROJECT_COLUMNS)
    if more:
        echo_err(f"Showing the first {limit} projects; more exist. Use --limit to see more.")


@app.command()
def fields(
    ctx: typer.Context,
    search: Annotated[
        str | None,
        typer.Option(
            "--search", "-s", help="Only fields whose name, id or JQL name contains this."
        ),
    ] = None,
    custom: Annotated[bool, typer.Option("--custom", help="Only custom fields.")] = False,
) -> None:
    """List issue fields and their ids (e.g. find the story points custom field)."""
    options: GlobalOptions = ctx.obj
    client, _ = _open_client(options)
    with client:
        found = service.find_fields(client, search, custom)
    emit([f.to_record() for f in found], resolve_format(options.format), columns=FIELD_COLUMNS)
