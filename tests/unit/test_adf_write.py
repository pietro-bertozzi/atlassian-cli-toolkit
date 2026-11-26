from typing import Any

import pytest

from atlassian_toolkit.jira.adf import adf_to_markdown
from atlassian_toolkit.jira.adf_write import markdown_to_adf


def content(markdown: str) -> list[dict[str, Any]]:
    doc = markdown_to_adf(markdown)
    assert doc["type"] == "doc"
    assert doc["version"] == 1
    return doc["content"]


def t(text: str, *marks: str | dict[str, Any]) -> dict[str, Any]:
    node: dict[str, Any] = {"type": "text", "text": text}
    if marks:
        node["marks"] = [{"type": m} if isinstance(m, str) else m for m in marks]
    return node


def para(*nodes: dict[str, Any]) -> dict[str, Any]:
    return {"type": "paragraph", "content": list(nodes)}


def test_paragraphs_and_line_breaks() -> None:
    assert content("one\ntwo\n\nthree") == [
        para(t("one"), {"type": "hardBreak"}, t("two")),
        para(t("three")),
    ]


def test_empty_text_gives_empty_doc() -> None:
    assert content("") == []
    assert content("\n \n") == []


def test_inline_marks() -> None:
    assert content("**b** *i* __b2__ _i2_ ~~s~~ `c`") == [
        para(
            t("b", "strong"),
            t(" "),
            t("i", "em"),
            t(" "),
            t("b2", "strong"),
            t(" "),
            t("i2", "em"),
            t(" "),
            t("s", "strike"),
            t(" "),
            t("c", "code"),
        )
    ]


def test_nested_marks_and_link() -> None:
    link = {"type": "link", "attrs": {"href": "https://example.com/a"}}
    assert content("see **[the docs](https://example.com/a)** now") == [
        para(t("see "), t("the docs", "strong", link), t(" now"))
    ]


def test_things_that_are_not_markup_stay_plain() -> None:
    assert content("snake_case_name and 2 * 3 * 4 and [x](javascript:alert)") == [
        para(t("snake_case_name and 2 * 3 * 4 and [x](javascript:alert)"))
    ]
    assert content("unclosed **bold and `code") == [para(t("unclosed **bold and `code"))]


def test_code_span_keeps_markup_literal() -> None:
    assert content("run `a **b** c` now") == [para(t("run "), t("a **b** c", "code"), t(" now"))]


def test_headings() -> None:
    assert content("# Title\n### Sub ###") == [
        {"type": "heading", "attrs": {"level": 1}, "content": [t("Title")]},
        {"type": "heading", "attrs": {"level": 3}, "content": [t("Sub")]},
    ]


def test_fenced_code_block_with_language() -> None:
    assert content("```python\nprint('**x**')\n\nx = 1\n```\nafter") == [
        {
            "type": "codeBlock",
            "attrs": {"language": "python"},
            "content": [t("print('**x**')\n\nx = 1")],
        },
        para(t("after")),
    ]


def test_unterminated_code_block_runs_to_end() -> None:
    assert content("~~~\ncode") == [{"type": "codeBlock", "content": [t("code")]}]


def test_bullet_list_with_one_nested_level() -> None:
    assert content("- a\n  - a1\n  - a2\n- b") == [
        {
            "type": "bulletList",
            "content": [
                {
                    "type": "listItem",
                    "content": [
                        para(t("a")),
                        {
                            "type": "bulletList",
                            "content": [
                                {"type": "listItem", "content": [para(t("a1"))]},
                                {"type": "listItem", "content": [para(t("a2"))]},
                            ],
                        },
                    ],
                },
                {"type": "listItem", "content": [para(t("b"))]},
            ],
        }
    ]


def test_ordered_list_keeps_start_number() -> None:
    blocks = content("3. c\n4. d")
    assert blocks[0]["type"] == "orderedList"
    assert blocks[0]["attrs"] == {"order": 3}
    assert len(blocks[0]["content"]) == 2


def test_list_then_paragraph() -> None:
    blocks = content("- a\n- b\n\ntext")
    assert [b["type"] for b in blocks] == ["bulletList", "paragraph"]


def test_list_item_continuation_line() -> None:
    assert content("- first\n  more") == [
        {
            "type": "bulletList",
            "content": [
                {
                    "type": "listItem",
                    "content": [para(t("first"), {"type": "hardBreak"}, t("more"))],
                }
            ],
        }
    ]


def test_crlf_input() -> None:
    assert content("a\r\nb") == content("a\nb")


def _no_empty_text(node: Any) -> bool:
    if isinstance(node, dict):
        if node.get("type") == "text" and not node.get("text"):
            return False
        return all(_no_empty_text(child) for child in node.get("content", []))
    return True


@pytest.mark.parametrize(
    "markdown",
    [
        "Plain text.",
        "## Heading\n\nSome **bold** and *italic* and `code`.",
        "- one\n- two\n  - nested",
        "1. first\n2. second",
        "```bash\natl jira mine\n```",
        "A [link](https://example.com) here.",
        "** * _ ~~ ` [ ] ( ) # - 1.",  # stray markup characters
    ],
)
def test_round_trip_keeps_text_and_never_emits_empty_text(markdown: str) -> None:
    doc = markdown_to_adf(markdown)
    assert _no_empty_text(doc)
    back = adf_to_markdown(doc)
    words = [w for w in markdown.replace("*", " ").replace("`", " ").split() if w.isalnum()]
    for word in words:
        assert word in back
