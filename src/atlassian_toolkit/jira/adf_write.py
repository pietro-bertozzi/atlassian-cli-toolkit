"""Markdown -> Atlassian Document Format (ADF), for text we send to Jira (e.g. comments).

Deliberately small and conservative, so Jira never rejects the document:

* Blocks: paragraphs, headings (``#``..``######``), bullet lists (``-``, ``*``, ``+``),
  ordered lists (``1.`` / ``1)``, start number kept), one level of list nesting (indent the
  nested item by 2+ spaces), fenced code blocks (`````` ``` `````` or ``~~~``, with language).
* Inline: ``**bold**`` / ``__bold__``, ``*italic*`` / ``_italic_``, ``~~strike~~``,
  ```code```, ``[text](https://...)`` links (http/https only).
* A line break inside a paragraph is kept as a line break (as people expect in Jira), not
  joined into one line as strict Markdown would.
* Everything else (quotes, tables, images, HTML, rules) is kept as plain text.

ADF reference: https://developer.atlassian.com/cloud/jira/platform/apis/document/structure/
"""

from __future__ import annotations

import re
from typing import Any

Node = dict[str, Any]
Mark = dict[str, Any]

_FENCE = re.compile(r"^(`{3,}|~{3,})\s*([\w+#.-]*)\s*$")
_HEADING = re.compile(r"^(#{1,6})\s+(.*?)\s*#*\s*$")
_BULLET = re.compile(r"^( *)[-*+]\s+(.*)$")
_ORDERED = re.compile(r"^( *)(\d{1,9})[.)]\s+(.*)$")
_LINK = re.compile(r"\[([^\]\n]+)\]\((https?://[^\s)]+)\)")
_NESTED_INDENT = 2


def markdown_to_adf(markdown: str) -> Node:
    """Convert Markdown text to an ADF ``doc`` node."""
    lines = markdown.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    return {"type": "doc", "version": 1, "content": _blocks(lines)}


# --- blocks ------------------------------------------------------------------------------------


def _blocks(lines: list[str]) -> list[Node]:
    blocks: list[Node] = []
    i = 0
    paragraph: list[str] = []

    def flush() -> None:
        if paragraph:
            node = _paragraph("\n".join(paragraph))
            if node is not None:
                blocks.append(node)
            paragraph.clear()

    while i < len(lines):
        line = lines[i]
        fence = None if line.startswith("    ") else _FENCE.match(line.strip())
        if fence:
            flush()
            block, i = _code_block(lines, i, fence.group(1), fence.group(2))
            blocks.append(block)
            continue
        heading = _HEADING.match(line)
        if heading:
            flush()
            content = _inline(heading.group(2))
            node: Node = {"type": "heading", "attrs": {"level": len(heading.group(1))}}
            if content:
                node["content"] = content
            blocks.append(node)
            i += 1
            continue
        if _list_marker(line) is not None and not line.startswith(" "):
            flush()
            block, i = _list(lines, i)
            blocks.append(block)
            continue
        if not line.strip():
            flush()
        else:
            paragraph.append(line.strip())
        i += 1
    flush()
    return blocks


def _paragraph(text: str) -> Node | None:
    content = _inline_with_breaks(text)
    return {"type": "paragraph", "content": content} if content else None


def _code_block(lines: list[str], start: int, fence: str, language: str) -> tuple[Node, int]:
    """Collect lines until a closing fence of the same kind (or the end of the text)."""
    body: list[str] = []
    i = start + 1
    while i < len(lines):
        stripped = lines[i].strip()
        if stripped.startswith(fence[0] * len(fence)) and not stripped.strip(fence[0]):
            i += 1
            break
        body.append(lines[i])
        i += 1
    node: Node = {"type": "codeBlock"}
    if language:
        node["attrs"] = {"language": language}
    code = "\n".join(body)
    if code:
        node["content"] = [{"type": "text", "text": code}]
    return node, i


def _list_marker(line: str) -> tuple[str, int, int | None, str] | None:
    """Return (kind, indent, number, text) for a list item line, else None."""
    bullet = _BULLET.match(line)
    if bullet:
        return "bulletList", len(bullet.group(1)), None, bullet.group(2)
    ordered = _ORDERED.match(line)
    if ordered:
        return "orderedList", len(ordered.group(1)), int(ordered.group(2)), ordered.group(3)
    return None


def _list(lines: list[str], start: int) -> tuple[Node, int]:
    """Parse a top-level list and its one level of nested items."""
    first = _list_marker(lines[start])
    assert first is not None
    kind, _, number, _ = first
    items: list[Node] = []
    i = start
    while i < len(lines):
        marker = _list_marker(lines[i])
        if marker is None:
            if lines[i].strip() and items and lines[i].startswith(" "):
                _append_text(items[-1], lines[i].strip())  # continuation line
                i += 1
                continue
            break
        item_kind, indent, _, text = marker
        if indent >= _NESTED_INDENT and items:
            nested, i = _nested_list(lines, i)
            items[-1]["content"].append(nested)
            continue
        if item_kind != kind or indent >= _NESTED_INDENT:
            break
        items.append({"type": "listItem", "content": [_item_paragraph(text)]})
        i += 1
    node: Node = {"type": kind, "content": items}
    if kind == "orderedList" and number is not None and number != 1:
        node["attrs"] = {"order": number}
    return node, i


def _nested_list(lines: list[str], start: int) -> tuple[Node, int]:
    first = _list_marker(lines[start])
    assert first is not None
    kind, _, number, _ = first
    items: list[Node] = []
    i = start
    while i < len(lines):
        marker = _list_marker(lines[i])
        if marker is None or marker[1] < _NESTED_INDENT or marker[0] != kind:
            break
        items.append({"type": "listItem", "content": [_item_paragraph(marker[3])]})
        i += 1
    node: Node = {"type": kind, "content": items}
    if kind == "orderedList" and number is not None and number != 1:
        node["attrs"] = {"order": number}
    return node, i


def _item_paragraph(text: str) -> Node:
    """A list item must start with a paragraph (it may be empty)."""
    content = _inline(text.strip())
    return {"type": "paragraph", "content": content} if content else {"type": "paragraph"}


def _append_text(item: Node, text: str) -> None:
    paragraph = item["content"][0]
    paragraph.setdefault("content", []).extend([{"type": "hardBreak"}, *_inline(text)])


# --- inline ------------------------------------------------------------------------------------


def _inline_with_breaks(text: str) -> list[Node]:
    content: list[Node] = []
    for index, line in enumerate(text.split("\n")):
        if index:
            content.append({"type": "hardBreak"})
        content.extend(_inline(line))
    return content


def _inline(text: str, marks: tuple[Mark, ...] = ()) -> list[Node]:
    """Parse inline Markdown into ADF text nodes (adjacent nodes with equal marks merged)."""
    nodes: list[Node] = []
    plain: list[str] = []
    i = 0

    def emit_plain() -> None:
        if plain:
            _add_text(nodes, "".join(plain), marks)
            plain.clear()

    while i < len(text):
        parsed = _try_span(text, i, marks)
        if parsed is not None:
            emit_plain()
            span_nodes, i = parsed
            for node in span_nodes:
                _add_text(nodes, node["text"], tuple(node.get("marks", ())))
            continue
        plain.append(text[i])
        i += 1
    emit_plain()
    return nodes


def _try_span(text: str, i: int, marks: tuple[Mark, ...]) -> tuple[list[Node], int] | None:
    char = text[i]
    if char == "`":
        run = len(text[i:]) - len(text[i:].lstrip("`"))
        end = text.find("`" * run, i + run)
        if end > i + run:
            code = text[i + run : end]
            if code.startswith(" ") and code.endswith(" ") and code.strip():
                code = code[1:-1]
            return [{"type": "text", "text": code, "marks": [{"type": "code"}]}], end + run
        return None
    if char == "[":
        link = _LINK.match(text, i)
        if link:
            mark = {"type": "link", "attrs": {"href": link.group(2)}}
            return _inline(link.group(1), (*marks, mark)), link.end()
        return None
    for delimiter, mark_type in (("**", "strong"), ("__", "strong"), ("~~", "strike")):
        if text.startswith(delimiter, i):
            end = text.find(delimiter, i + 2)
            if end > i + 2 and not text[i + 2].isspace() and not text[end - 1].isspace():
                return _inline(text[i + 2 : end], (*marks, {"type": mark_type})), end + 2
            return None
    if char in "*_":
        if char == "_" and i > 0 and text[i - 1].isalnum():
            return None  # snake_case words are not emphasis
        end = _closing_single(text, i, char)
        if end is not None:
            return _inline(text[i + 1 : end], (*marks, {"type": "em"})), end + 1
    return None


def _closing_single(text: str, start: int, char: str) -> int | None:
    if start + 1 >= len(text) or text[start + 1].isspace() or text[start + 1] == char:
        return None
    end = start + 1
    while True:
        end = text.find(char, end)
        if end == -1:
            return None
        doubled = text.startswith(char * 2, end)
        after = text[end + 1] if end + 1 < len(text) else ""
        if not doubled and not text[end - 1].isspace():
            if char == "_" and after.isalnum():
                end += 1
                continue
            return end
        end += 2 if doubled else 1


def _add_text(nodes: list[Node], text: str, marks: tuple[Mark, ...]) -> None:
    if not text:
        return  # ADF text nodes must not be empty
    if nodes and nodes[-1].get("marks", []) == list(marks):
        nodes[-1]["text"] += text
        return
    node: Node = {"type": "text", "text": text}
    if marks:
        node["marks"] = list(marks)
    nodes.append(node)
