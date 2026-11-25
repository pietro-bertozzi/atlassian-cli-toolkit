"""Atlassian Document Format (ADF) -> Markdown.

Jira REST API v3 returns rich text (issue descriptions, comments) as ADF: a JSON tree whose
root is ``{"type": "doc", "version": 1, "content": [...]}``. Each node has a ``type``, and
optionally ``content`` (child nodes), ``attrs`` (node settings) and, for ``text`` nodes,
``text`` and ``marks`` (formatting).

Docs: https://developer.atlassian.com/cloud/jira/platform/apis/document/structure/

Behaviour:

* Supported nodes and marks are converted to GitHub-flavoured Markdown.
* Unknown nodes keep their text: their children are converted, their own semantics are lost.
* Visual-only marks (underline, text colour, sub/superscript, border) are dropped.
* Attachments (media nodes) become an ``[attachment]`` placeholder; nothing is downloaded.
* Malformed input never raises: bad nodes are skipped. Nesting deeper than ``MAX_DEPTH`` is
  cut off, so hostile input cannot exhaust Python's recursion limit.
* Text is untrusted data. It is not interpreted; it is escaped only where it would break the
  output structure (table cells, code spans). Markdown characters inside plain text are kept
  as-is, so text such as ``*word*`` renders as emphasis.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Mapping
from datetime import UTC, datetime
from typing import Any

MAX_DEPTH = 100
ATTACHMENT = "[attachment]"
HARD_BREAK = "\\\n"  # CommonMark backslash line break; survives whitespace stripping

Node = Mapping[str, Any]

INLINE_TYPES = frozenset(
    {"text", "hardBreak", "mention", "emoji", "status", "date", "inlineCard", "mediaInline"}
)


def adf_to_markdown(doc: Any) -> str:
    """Convert an ADF document (or any ADF node) to Markdown. Returns "" for empty input."""
    if not isinstance(doc, Mapping):
        return ""
    text = _block(doc, 0)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


# --- tree helpers ----------------------------------------------------------------------------


def _children(node: Node) -> list[Node]:
    content = node.get("content")
    if not isinstance(content, list):
        return []
    return [child for child in content if isinstance(child, Mapping)]


def _attr(node: Node, name: str) -> Any:
    attrs = node.get("attrs")
    return attrs.get(name) if isinstance(attrs, Mapping) else None


def _str_attr(node: Node, name: str) -> str | None:
    value = _attr(node, name)
    return value if isinstance(value, str) and value else None


def _prefix_lines(text: str, first: str, rest: str) -> str:
    """Prefix the first line with ``first`` and the following non-empty lines with ``rest``."""
    lines = text.split("\n")
    out = [first + lines[0]]
    out.extend(rest + line if line else rest.rstrip() for line in lines[1:])
    return "\n".join(out)


# --- blocks ----------------------------------------------------------------------------------


def _block(node: Node, depth: int) -> str:
    """Render one node as a block (a paragraph-level chunk of Markdown)."""
    if depth > MAX_DEPTH:
        return ""
    node_type = node.get("type")
    if node_type in INLINE_TYPES:
        return _inline_node(node, depth)
    handler = _BLOCK_HANDLERS.get(node_type) if isinstance(node_type, str) else None
    if handler is not None:
        return handler(node, depth)
    return _unknown(node, depth)


def _blocks(node: Node, depth: int, sep: str = "\n\n") -> str:
    parts = (_block(child, depth + 1) for child in _children(node))
    return sep.join(part for part in parts if part)


def _unknown(node: Node, depth: int) -> str:
    """Keep the text of nodes we do not know (e.g. ``doc`` wrappers, future node types)."""
    children = _children(node)
    if children and all(child.get("type") in INLINE_TYPES for child in children):
        return _inlines(node, depth)
    return _blocks(node, depth)


def _paragraph(node: Node, depth: int) -> str:
    text = _inlines(node, depth)
    while text.endswith(HARD_BREAK):
        text = text[: -len(HARD_BREAK)]
    return text


def _heading(node: Node, depth: int) -> str:
    level = _attr(node, "level")
    if not isinstance(level, int) or isinstance(level, bool):
        level = 1
    level = min(max(level, 1), 6)
    text = _single_line(_inlines(node, depth))
    return f"{'#' * level} {text}" if text else ""


def _bullet_list(node: Node, depth: int) -> str:
    return _list(node, depth, start=None)


def _ordered_list(node: Node, depth: int) -> str:
    order = _attr(node, "order")
    start = order if isinstance(order, int) and not isinstance(order, bool) and order >= 0 else 1
    return _list(node, depth, start=start)


def _list(node: Node, depth: int, start: int | None) -> str:
    items = []
    for index, item in enumerate(_children(node)):
        marker = "- " if start is None else f"{start + index}. "
        body = _block(item, depth + 1)
        items.append(_prefix_lines(body, marker, " " * len(marker)))
    return "\n".join(items)


def _list_item(node: Node, depth: int) -> str:
    return _blocks(node, depth, sep="\n")


def _code_block(node: Node, depth: int) -> str:
    code = "".join(
        child["text"]
        for child in _children(node)
        if child.get("type") == "text" and isinstance(child.get("text"), str)
    )
    longest = max((len(run) for run in re.findall(r"`+", code)), default=0)
    fence = "`" * max(3, longest + 1)
    language = _str_attr(node, "language") or ""
    if not re.fullmatch(r"[\w+#.-]*", language):
        language = ""
    return f"{fence}{language}\n{code}\n{fence}"


def _blockquote(node: Node, depth: int) -> str:
    return _quote(_blocks(node, depth))


def _quote(text: str) -> str:
    return _prefix_lines(text, "> ", "> ") if text else ""


def _panel(node: Node, depth: int) -> str:
    label = (_str_attr(node, "panelType") or "panel").capitalize()
    body = _blocks(node, depth)
    return _quote(f"**{label}:**\n{body}" if body else f"**{label}:**")


def _rule(node: Node, depth: int) -> str:
    return "---"


def _expand(node: Node, depth: int) -> str:
    title = _str_attr(node, "title")
    body = _blocks(node, depth)
    if title:
        return f"**{_single_line(title)}**\n\n{body}" if body else f"**{_single_line(title)}**"
    return body


def _media_group(node: Node, depth: int) -> str:
    count = sum(1 for child in _children(node) if child.get("type") == "media")
    return " ".join([ATTACHMENT] * max(count, 1))


def _media(node: Node, depth: int) -> str:
    return ATTACHMENT


def _table(node: Node, depth: int) -> str:
    rows: list[list[str]] = []
    header_row = False
    for index, row in enumerate(_children(node)):
        cells = _children(row)
        if index == 0:
            header_row = bool(cells) and all(c.get("type") == "tableHeader" for c in cells)
        rows.append([_table_cell(cell, depth + 1) for cell in cells])
    width = max((len(row) for row in rows), default=0)
    if width == 0:
        return ""
    rows = [row + [""] * (width - len(row)) for row in rows]
    header = rows.pop(0) if header_row else [""] * width
    lines = [_table_line(header), _table_line(["---"] * width)]
    lines.extend(_table_line(row) for row in rows)
    return "\n".join(lines)


def _table_cell(cell: Node, depth: int) -> str:
    text = _blocks(cell, depth, sep=" ")
    text = _single_line(text)
    return text.replace("\\", "\\\\").replace("|", "\\|")


def _table_line(cells: list[str]) -> str:
    return "| " + " | ".join(cells) + " |"


def _single_line(text: str) -> str:
    return " ".join(text.replace(HARD_BREAK, " ").split())


# --- inline ----------------------------------------------------------------------------------


def _inlines(node: Node, depth: int) -> str:
    return "".join(_inline_node(child, depth + 1) for child in _children(node))


def _inline_node(node: Node, depth: int) -> str:
    if depth > MAX_DEPTH:
        return ""
    node_type = node.get("type")
    handler = _INLINE_HANDLERS.get(node_type) if isinstance(node_type, str) else None
    if handler is not None:
        return handler(node)
    return _single_line(_unknown(node, depth))


def _text(node: Node) -> str:
    text = node.get("text")
    if not isinstance(text, str) or not text:
        return ""
    raw_marks = node.get("marks")
    marks = [m for m in raw_marks if isinstance(m, Mapping)] if isinstance(raw_marks, list) else []
    mark_types = {m.get("type") for m in marks}
    if "code" in mark_types:
        text = _code_span(text)
    else:
        if "strike" in mark_types:
            text = _wrap(text, "~~")
        if "em" in mark_types:
            text = _wrap(text, "*")
        if "strong" in mark_types:
            text = _wrap(text, "**")
    for mark in marks:
        if mark.get("type") == "link":
            href = _str_attr(mark, "href")
            if href:
                text = _link(text, href)
    return text


def _wrap(text: str, marker: str) -> str:
    """Wrap ``text`` in an emphasis marker, keeping surrounding whitespace outside it."""
    core = text.strip()
    if not core:
        return text
    lead = text[: len(text) - len(text.lstrip())]
    trail = text[len(text.rstrip()) :]
    return f"{lead}{marker}{core}{marker}{trail}"


def _code_span(text: str) -> str:
    longest = max((len(run) for run in re.findall(r"`+", text)), default=0)
    ticks = "`" * (longest + 1)
    pad = " " if text.startswith("`") or text.endswith("`") else ""
    return f"{ticks}{pad}{text}{pad}{ticks}"


def _link(text: str, href: str) -> str:
    safe = href.replace(" ", "%20").replace("(", "%28").replace(")", "%29")
    label = text.replace("[", "\\[").replace("]", "\\]")
    return f"[{label}]({safe})"


def _hard_break(node: Node) -> str:
    return HARD_BREAK


def _mention(node: Node) -> str:
    text = _str_attr(node, "text")
    if text:
        return text
    account = _str_attr(node, "id")
    return f"@{account}" if account else ""


def _emoji(node: Node) -> str:
    return _str_attr(node, "text") or _str_attr(node, "shortName") or ""


def _status(node: Node) -> str:
    text = _str_attr(node, "text")
    return f"[{text}]" if text else ""


def _date(node: Node) -> str:
    """Render a date node as YYYY-MM-DD (UTC).

    The docs define ``timestamp`` as a string without stating the unit; values above 1e11 are
    treated as milliseconds, smaller ones as seconds. Unparsable values are shown as-is.
    """
    raw = _attr(node, "timestamp")
    if not isinstance(raw, str | int) or isinstance(raw, bool):
        return ""
    try:
        value = int(raw)
        seconds = value / 1000 if abs(value) > 1e11 else value
        return datetime.fromtimestamp(seconds, UTC).date().isoformat()
    except (ValueError, OverflowError, OSError):
        return str(raw)


def _inline_card(node: Node) -> str:
    url = _str_attr(node, "url")
    return f"<{url}>" if url else ""


def _media_inline(node: Node) -> str:
    return ATTACHMENT


_BLOCK_HANDLERS: dict[str, Callable[[Node, int], str]] = {
    "paragraph": _paragraph,
    "heading": _heading,
    "bulletList": _bullet_list,
    "orderedList": _ordered_list,
    "listItem": _list_item,
    "codeBlock": _code_block,
    "blockquote": _blockquote,
    "panel": _panel,
    "rule": _rule,
    "expand": _expand,
    "nestedExpand": _expand,
    "table": _table,
    "mediaSingle": _media,
    "mediaGroup": _media_group,
    "media": _media,
}

_INLINE_HANDLERS: dict[str, Callable[[Node], str]] = {
    "text": _text,
    "hardBreak": _hard_break,
    "mention": _mention,
    "emoji": _emoji,
    "status": _status,
    "date": _date,
    "inlineCard": _inline_card,
    "mediaInline": _media_inline,
}
