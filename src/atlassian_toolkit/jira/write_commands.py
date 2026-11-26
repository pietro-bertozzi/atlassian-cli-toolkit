"""``atl jira issue comment|transition|assign``: the commands that change data in Jira.

Registered on the ``issue`` sub-app by ``commands.py``. Every command here follows the write
safety model described below and in docs/jira.md, "Write commands".
"""

import sys
from pathlib import Path
from typing import Annotated
from urllib.parse import quote

import typer

from atlassian_toolkit.core.client import JiraClient
from atlassian_toolkit.core.context import GlobalOptions
from atlassian_toolkit.core.errors import UsageError
from atlassian_toolkit.core.output import echo_err, emit, resolve_format
from atlassian_toolkit.jira import service
from atlassian_toolkit.jira.connect import open_client, selected_profile
from atlassian_toolkit.jira.models import UserRef

# Safety model (docs/jira.md, "Write commands"):
# 1. A preview is always printed on stderr before anything is sent.
# 2. --dry-run: preview only. Otherwise a terminal user is asked y/N; non-interactive callers
#    (scripts, agents) must pass --yes.
# 3. The client never retries a POST that may have been applied (see core/client.py).
# Further layers live outside the CLI: token scopes (a read-only scoped token cannot write)
# and, for Claude Code, the atl-jira skill pre-approves read commands only.

YesOption = Annotated[
    bool,
    typer.Option("--yes", "-y", help="Do not ask for confirmation (needed when not interactive)."),
]
DryRunOption = Annotated[
    bool, typer.Option("--dry-run", help="Show what would be sent; send nothing.")
]


def _open_client(options: GlobalOptions) -> JiraClient:
    """A client for the selected profile."""
    return open_client(*selected_profile(options.profile))


def _is_interactive() -> bool:
    """True when a person can answer a prompt (stdin and stderr are terminals)."""
    return sys.stdin.isatty() and sys.stderr.isatty()


def _approve_write(preview: str, yes: bool, dry_run: bool) -> bool:
    """Apply the write safety model. Return True to send, False for a dry run."""
    echo_err(preview)
    if dry_run:
        echo_err("Dry run: nothing was sent.")
        return False
    if yes:
        return True
    if _is_interactive():
        if typer.confirm("Proceed?", default=False, err=True):
            return True
        raise UsageError("Cancelled: nothing was sent.")
    raise UsageError(
        "Not confirmed: nothing was sent. Re-run with --yes to perform this change "
        "(or --dry-run to preview it)."
    )


def _read_body(body: str | None, body_file: Path | None) -> str:
    """Comment text from --body or --body-file ('-' = stdin); exactly one is required."""
    if (body is None) == (body_file is None):
        raise UsageError("Give the comment text with exactly one of --body or --body-file.")
    if body_file is not None:
        if str(body_file) == "-":
            text = sys.stdin.read()
        else:
            try:
                text = body_file.expanduser().read_text(encoding="utf-8-sig")
            except OSError as exc:
                raise UsageError(f"Cannot read {body_file} ({type(exc).__name__}).") from None
    else:
        text = body or ""
    if not text.strip():
        raise UsageError("The comment is empty. Nothing was sent.")
    return text.strip("\n")


def issue_comment(
    ctx: typer.Context,
    key: Annotated[str, typer.Argument(help="Issue key (e.g. DEMO-123) or numeric issue id.")],
    body: Annotated[str | None, typer.Option("--body", help="Comment text (Markdown).")] = None,
    body_file: Annotated[
        Path | None,
        typer.Option("--body-file", help="Read the comment (Markdown) from a file; '-' = stdin."),
    ] = None,
    yes: YesOption = False,
    dry_run: DryRunOption = False,
) -> None:
    """WRITE: add a comment written in Markdown to an issue."""
    options: GlobalOptions = ctx.obj
    text = _read_body(body, body_file)
    client = _open_client(options)
    preview = f"About to add this comment to {key}:\n-----\n{text}\n-----"
    with client:
        if not _approve_write(preview, yes, dry_run):
            emit(
                {"key": key, "dry_run": True, "request": {
                    "method": "POST", "path": f"/rest/api/3/issue/{quote(key, safe='')}/comment",
                    "body": service.comment_request(text)}},
                resolve_format(options.format),
            )  # fmt: skip
            return
        comment = service.add_comment(client, key, text)
    echo_err(f"Comment {comment.id} added to {key}.")
    emit(
        {"key": key, "dry_run": False, "comment_id": comment.id, "created": comment.created},
        resolve_format(options.format),
    )


def issue_transition(
    ctx: typer.Context,
    key: Annotated[str, typer.Argument(help="Issue key (e.g. DEMO-123) or numeric issue id.")],
    to: Annotated[
        str,
        typer.Option("--to", help='Transition name or target status, e.g. "In Review".'),
    ],
    yes: YesOption = False,
    dry_run: DryRunOption = False,
) -> None:
    """WRITE: move an issue to another status (available moves: 'atl jira issue get KEY')."""
    options: GlobalOptions = ctx.obj
    client = _open_client(options)
    with client:
        chosen = service.choose_transition(service.list_transitions(client, key), to)
        preview = (
            f"About to move {key} with transition {chosen.name!r} -> status {chosen.to_status!r}."
        )
        if chosen.has_screen:
            preview += (
                "\nNote: this transition has a screen in Jira; if it requires fields, Jira will "
                "reject it and you must do it in the browser."
            )
        record = {"key": key, "transition": chosen.name, "transition_id": chosen.id,
                  "to_status": chosen.to_status}  # fmt: skip
        if not _approve_write(preview, yes, dry_run):
            emit({**record, "dry_run": True}, resolve_format(options.format))
            return
        service.transition_issue(client, key, chosen.id)
    echo_err(f"{key} moved to {chosen.to_status!r}.")
    emit({**record, "dry_run": False}, resolve_format(options.format))


def issue_assign(
    ctx: typer.Context,
    key: Annotated[str, typer.Argument(help="Issue key (e.g. DEMO-123) or numeric issue id.")],
    to: Annotated[
        str | None,
        typer.Option("--to", help="'me', or a name or email to search among assignable users."),
    ] = None,
    account_id: Annotated[
        str | None, typer.Option("--account-id", help="Assign to this exact Atlassian account id.")
    ] = None,
    unassign: Annotated[bool, typer.Option("--unassign", help="Remove the assignee.")] = False,
    yes: YesOption = False,
    dry_run: DryRunOption = False,
) -> None:
    """WRITE: assign an issue (to me, to someone, or to nobody)."""
    if sum((to is not None, account_id is not None, unassign)) != 1:
        raise UsageError("Use exactly one of --to, --account-id or --unassign.")
    options: GlobalOptions = ctx.obj
    client = _open_client(options)
    with client:
        user: UserRef | None = None
        if to is not None:
            user = service.find_assignee(client, key, to)
            target_id: str | None = user.account_id
            target = f"{user.display_name} ({user.account_id})"
        elif account_id is not None:
            target_id, target = account_id, f"account {account_id}"
        else:
            target_id, target = None, "nobody (unassigned)"
        preview = f"About to assign {key} to {target}."
        record = {"key": key, "assignee": user.display_name if user else None,
                  "account_id": target_id}  # fmt: skip
        if not _approve_write(preview, yes, dry_run):
            emit({**record, "dry_run": True}, resolve_format(options.format))
            return
        service.assign_issue(client, key, target_id)
    echo_err(f"{key} assigned to {target}.")
    emit({**record, "dry_run": False}, resolve_format(options.format))
