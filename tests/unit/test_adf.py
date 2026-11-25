from typing import Any

import pytest

from atlassian_toolkit.jira.adf import MAX_DEPTH, adf_to_markdown


def doc(*content: dict[str, Any]) -> dict[str, Any]:
    return {"type": "doc", "version": 1, "content": list(content)}


def text(value: str, *marks: str | dict[str, Any]) -> dict[str, Any]:
    node: dict[str, Any] = {"type": "text", "text": value}
    if marks:
        node["marks"] = [{"type": m} if isinstance(m, str) else m for m in marks]
    return node


def para(*content: dict[str, Any]) -> dict[str, Any]:
    return {"type": "paragraph", "content": list(content)}


def item(*content: dict[str, Any]) -> dict[str, Any]:
    return {"type": "listItem", "content": list(content)}


def bullets(*items: dict[str, Any]) -> dict[str, Any]:
    return {"type": "bulletList", "content": list(items)}


@pytest.mark.parametrize("value", [None, "", "plain", 42, [], {}, {"type": "doc"}])
def test_empty_or_invalid_input(value: Any) -> None:
    assert adf_to_markdown(value) == ""


def test_paragraphs_are_separated_by_blank_line() -> None:
    assert adf_to_markdown(doc(para(text("one")), para(text("two")))) == "one\n\ntwo"


def test_marks() -> None:
    result = adf_to_markdown(
        doc(
            para(
                text("bold", "strong"),
                text(" "),
                text("it", "em"),
                text(" "),
                text("gone", "strike"),
                text(" "),
                text("both", "strong", "em"),
                text(" "),
                text("under", "underline", {"type": "textColor", "attrs": {"color": "#ff0000"}}),
            )
        )
    )
    assert result == "**bold** *it* ~~gone~~ ***both*** under"


def test_emphasis_keeps_whitespace_outside_markers() -> None:
    assert adf_to_markdown(doc(para(text("a"), text(" b ", "strong"), text("c")))) == "a **b** c"


def test_code_mark_and_backticks() -> None:
    result = adf_to_markdown(doc(para(text("x = 1", "code"), text(" "), text("a`b", "code"))))
    assert result == "`x = 1` ``a`b``"


def test_link_mark() -> None:
    link = {"type": "link", "attrs": {"href": "https://example.com/a b"}}
    assert adf_to_markdown(doc(para(text("site", link)))) == "[site](https://example.com/a%20b)"


def test_hard_break() -> None:
    result = adf_to_markdown(doc(para(text("a"), {"type": "hardBreak"}, text("b"))))
    assert result == "a\\\nb"


def test_heading_levels_are_clamped() -> None:
    assert (
        adf_to_markdown(doc({"type": "heading", "attrs": {"level": 2}, "content": [text("T")]}))
        == "## T"
    )
    assert (
        adf_to_markdown(doc({"type": "heading", "attrs": {"level": 9}, "content": [text("T")]}))
        == "###### T"
    )
    assert adf_to_markdown(doc({"type": "heading", "content": [text("T")]})) == "# T"


def test_nested_bullet_list() -> None:
    tree = doc(bullets(item(para(text("a")), bullets(item(para(text("a1")))))), para(text("x")))
    assert adf_to_markdown(tree) == "- a\n  - a1\n\nx"


def test_ordered_list_with_custom_start() -> None:
    tree = doc(
        {
            "type": "orderedList",
            "attrs": {"order": 3},
            "content": [item(para(text("c"))), item(para(text("d")))],
        }
    )
    assert adf_to_markdown(tree) == "3. c\n4. d"


def test_code_block_with_language_and_backticks() -> None:
    tree = doc(
        {
            "type": "codeBlock",
            "attrs": {"language": "python"},
            "content": [text("print('```')")],
        }
    )
    assert adf_to_markdown(tree) == "````python\nprint('```')\n````"


def test_code_block_drops_suspicious_language() -> None:
    tree = doc({"type": "codeBlock", "attrs": {"language": "x\n# hi"}, "content": [text("y")]})
    assert adf_to_markdown(tree) == "```\ny\n```"


def test_blockquote_and_rule() -> None:
    tree = doc(
        {"type": "blockquote", "content": [para(text("q1")), para(text("q2"))]},
        {"type": "rule"},
    )
    assert adf_to_markdown(tree) == "> q1\n>\n> q2\n\n---"


def test_panel() -> None:
    tree = doc({"type": "panel", "attrs": {"panelType": "warning"}, "content": [para(text("x"))]})
    assert adf_to_markdown(tree) == "> **Warning:**\n> x"


def cell(kind: str, value: str) -> dict[str, Any]:
    return {"type": kind, "content": [para(text(value))]}


def row(*cells: dict[str, Any]) -> dict[str, Any]:
    return {"type": "tableRow", "content": list(cells)}


def test_table_with_header_row() -> None:
    tree = doc(
        {
            "type": "table",
            "content": [
                row(cell("tableHeader", "H1"), cell("tableHeader", "H2")),
                row(cell("tableCell", "a|b"), cell("tableCell", "c")),
            ],
        }
    )
    assert adf_to_markdown(tree) == "| H1 | H2 |\n| --- | --- |\n| a\\|b | c |"


def test_table_without_header_row_and_ragged_rows() -> None:
    tree = doc(
        {
            "type": "table",
            "content": [
                row(cell("tableCell", "a"), cell("tableCell", "b")),
                row(cell("tableCell", "c")),
            ],
        }
    )
    assert adf_to_markdown(tree) == "|  |  |\n| --- | --- |\n| a | b |\n| c |  |"


def test_table_cell_is_flattened_to_one_line() -> None:
    multi = {"type": "tableCell", "content": [para(text("one")), para(text("two"))]}
    tree = doc({"type": "table", "content": [row(multi)]})
    assert adf_to_markdown(tree).endswith("| one two |")


def test_expand() -> None:
    tree = doc({"type": "expand", "attrs": {"title": "More"}, "content": [para(text("hidden"))]})
    assert adf_to_markdown(tree) == "**More**\n\nhidden"


def test_media_placeholders() -> None:
    media = {"type": "media", "attrs": {"id": "abc", "type": "file", "collection": "c"}}
    tree = doc(
        {"type": "mediaSingle", "attrs": {"layout": "center"}, "content": [media]},
        {"type": "mediaGroup", "content": [media, media]},
        para(text("see "), {"type": "mediaInline", "attrs": {"id": "x"}}),
    )
    assert adf_to_markdown(tree) == "[attachment]\n\n[attachment] [attachment]\n\nsee [attachment]"


def test_inline_nodes() -> None:
    tree = doc(
        para(
            {"type": "mention", "attrs": {"id": "abc123", "text": "@Alice Example"}},
            text(" "),
            {"type": "mention", "attrs": {"id": "def456"}},
            text(" "),
            {"type": "emoji", "attrs": {"shortName": ":grinning:", "text": "😀"}},
            {"type": "emoji", "attrs": {"shortName": ":custom:"}},
            text(" "),
            {"type": "status", "attrs": {"text": "IN PROGRESS", "color": "blue"}},
            text(" "),
            {"type": "inlineCard", "attrs": {"url": "https://example.atlassian.net/browse/DEMO-1"}},
        )
    )
    assert adf_to_markdown(tree) == (
        "@Alice Example @def456 😀:custom: [IN PROGRESS] "
        "<https://example.atlassian.net/browse/DEMO-1>"
    )


@pytest.mark.parametrize(
    ("timestamp", "expected"),
    [
        ("1582152559", "2020-02-19"),  # seconds
        ("1582152559000", "2020-02-19"),  # milliseconds
        ("not-a-date", "not-a-date"),
    ],
)
def test_date(timestamp: str, expected: str) -> None:
    tree = doc(para({"type": "date", "attrs": {"timestamp": timestamp}}))
    assert adf_to_markdown(tree) == expected


def test_unknown_nodes_keep_their_text() -> None:
    tree = doc(
        {
            "type": "taskList",
            "content": [{"type": "taskItem", "content": [text("buy milk")]}],
        },
        {"type": "someFutureBlock", "content": [para(text("future"))]},
    )
    assert adf_to_markdown(tree) == "buy milk\n\nfuture"


def test_malformed_nodes_are_skipped() -> None:
    tree = doc(
        "not a node",  # type: ignore[arg-type]
        {"content": [para(text("no type"))]},
        para(text("ok"), {"type": "text", "text": 5}, {"type": "text", "text": "!", "marks": 3}),
        {"type": "heading", "attrs": "bad", "content": "bad"},
        {"type": "orderedList", "attrs": {"order": "x"}, "content": [item(para(text("i")))]},
    )
    assert adf_to_markdown(tree) == "no type\n\nok!\n\n1. i"


def test_depth_cap_stops_deep_nesting() -> None:
    node: dict[str, Any] = para(text("deep"))
    for _ in range(MAX_DEPTH * 20):
        node = {"type": "blockquote", "content": [node]}
    assert adf_to_markdown(doc(node)) == ""
