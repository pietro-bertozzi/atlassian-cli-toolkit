"""Renderers for command results: json, table, markdown.

Rules (see CLAUDE.md section 7):

* Data goes to stdout. Messages, warnings and errors go to stderr.
* ``json`` output is plain, valid JSON only: no colours, banners or progress output.
* The default format is ``table`` on an interactive terminal and ``json`` otherwise.
* Values coming from Jira are untrusted: they are never interpreted as Rich markup.
"""

from __future__ import annotations

import json
import sys
from collections.abc import Mapping, Sequence
from enum import StrEnum
from typing import Any, TextIO

from rich.console import Console
from rich.table import Table
from rich.text import Text


class OutputFormat(StrEnum):
    """Supported ``--format`` values."""

    TABLE = "table"
    JSON = "json"
    MARKDOWN = "markdown"


Record = Mapping[str, Any]


def resolve_format(
    explicit: OutputFormat | None, stdout_is_tty: bool | None = None
) -> OutputFormat:
    """Return ``explicit`` or the default: table on a TTY, json otherwise."""
    if explicit is not None:
        return explicit
    if stdout_is_tty is None:
        stdout_is_tty = sys.stdout.isatty()
    return OutputFormat.TABLE if stdout_is_tty else OutputFormat.JSON


def configure_stdio() -> None:
    """Force UTF-8 on stdout/stderr (the Windows console default is not UTF-8)."""
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            reconfigure(encoding="utf-8")


def emit(
    data: Record | Sequence[Record],
    fmt: OutputFormat,
    *,
    columns: Sequence[str] | None = None,
    stream: TextIO | None = None,
) -> None:
    """Render ``data`` (one record or a list of records) to ``stream`` (default: stdout).

    ``columns`` selects and orders the keys shown by ``table`` and ``markdown`` for a list of
    records. ``json`` always outputs the complete data, so its keys are the stable contract.
    """
    out = stream if stream is not None else sys.stdout
    if fmt is OutputFormat.JSON:
        out.write(render_json(data) + "\n")
    elif fmt is OutputFormat.MARKDOWN:
        text = render_markdown(data, columns)
        if text:
            out.write(text + "\n")
        else:
            echo_err("No results.")
    else:
        render_table(data, columns, out)


def render_json(data: Record | Sequence[Record]) -> str:
    """Return pretty-printed JSON, keeping non-ASCII characters readable."""
    return json.dumps(data, indent=2, ensure_ascii=False, default=str)


def render_markdown(data: Record | Sequence[Record], columns: Sequence[str] | None = None) -> str:
    """Return a GitHub-flavoured Markdown table (list) or key/value bullet list (record)."""
    if isinstance(data, Mapping):
        return "\n".join(f"- **{key}**: {_md_inline(_cell(value))}" for key, value in data.items())
    if not data:
        return ""
    keys = _columns(data, columns)
    lines = [
        "| " + " | ".join(keys) + " |",
        "| " + " | ".join("---" for _ in keys) + " |",
    ]
    for record in data:
        lines.append("| " + " | ".join(_md_inline(_cell(record.get(k))) for k in keys) + " |")
    return "\n".join(lines)


def render_table(
    data: Record | Sequence[Record],
    columns: Sequence[str] | None,
    stream: TextIO,
) -> None:
    """Render a Rich table: key/value rows for a record, one row per record for a list.

    On a terminal Rich uses the terminal width. When writing to a pipe or file there is no real
    width (Rich would assume 80 and crop wide tables), so a generous fixed width is used.
    """
    width = None if _is_terminal(stream) else NON_TERMINAL_TABLE_WIDTH
    console = Console(file=stream, highlight=False, soft_wrap=False, width=width)
    if isinstance(data, Mapping):
        table = Table(show_header=False)
        table.add_column(style="bold")
        table.add_column()
        for key, value in data.items():
            table.add_row(Text(key), Text(_cell(value)))
    else:
        if not data:
            echo_err("No results.")
            return
        keys = _columns(data, columns)
        table = Table()
        for key in keys:
            # Never truncate a header: it may be an id the reader must copy (customfield_10016).
            table.add_column(key, min_width=len(key))
        for record in data:
            table.add_row(*(Text(_cell(record.get(k))) for k in keys))
    console.print(table)


NON_TERMINAL_TABLE_WIDTH = 160


def _is_terminal(stream: TextIO) -> bool:
    isatty = getattr(stream, "isatty", None)
    try:
        return bool(isatty()) if isatty is not None else False
    except ValueError:  # closed stream
        return False


def echo_err(message: str) -> None:
    """Write a message (log, warning, error) to stderr."""
    print(message, file=sys.stderr)


def _columns(records: Sequence[Record], columns: Sequence[str] | None) -> list[str]:
    if columns:
        return list(columns)
    return list(records[0].keys())


def _cell(value: Any) -> str:
    """Convert any value to display text."""
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, Sequence):
        return ", ".join(_cell(item) for item in value)
    if isinstance(value, Mapping):
        return json.dumps(value, ensure_ascii=False, default=str)
    return str(value)


def _md_inline(text: str) -> str:
    """Make text safe inside a single Markdown table cell or bullet."""
    return text.replace("\\", "\\\\").replace("|", "\\|").replace("\r", "").replace("\n", "<br>")
