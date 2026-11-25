import io
import json

import pytest

from atlassian_toolkit.core.output import OutputFormat, emit, resolve_format

RECORDS = [
    {"key": "DEMO-1", "summary": "First | pipe", "labels": ["a", "b"], "done": False},
    {"key": "DEMO-2", "summary": "Zweite Änderung", "labels": [], "done": True},
]


def run(data, fmt, columns=None) -> str:
    buffer = io.StringIO()
    emit(data, fmt, columns=columns, stream=buffer)
    return buffer.getvalue()


def test_default_format_depends_on_tty() -> None:
    assert resolve_format(None, stdout_is_tty=True) is OutputFormat.TABLE
    assert resolve_format(None, stdout_is_tty=False) is OutputFormat.JSON


def test_explicit_format_wins() -> None:
    assert resolve_format(OutputFormat.MARKDOWN, stdout_is_tty=False) is OutputFormat.MARKDOWN


def test_json_is_only_valid_json_with_all_keys() -> None:
    text = run(RECORDS, OutputFormat.JSON, columns=["key"])
    assert json.loads(text) == RECORDS
    assert "Änderung" in text  # not escaped


def test_json_single_record() -> None:
    assert json.loads(run(RECORDS[0], OutputFormat.JSON)) == RECORDS[0]


def test_markdown_table_escapes_pipes_and_selects_columns() -> None:
    text = run(RECORDS, OutputFormat.MARKDOWN, columns=["key", "summary"])
    lines = text.splitlines()
    assert lines[0] == "| key | summary |"
    assert lines[1] == "| --- | --- |"
    assert lines[2] == "| DEMO-1 | First \\| pipe |"


def test_markdown_newlines_stay_in_one_row() -> None:
    text = run([{"a": "line1\nline2"}], OutputFormat.MARKDOWN)
    assert text.splitlines()[2] == "| line1<br>line2 |"


def test_markdown_record_is_bullet_list() -> None:
    text = run({"key": "DEMO-1", "labels": ["a", "b"]}, OutputFormat.MARKDOWN)
    assert text.splitlines() == ["- **key**: DEMO-1", "- **labels**: a, b"]


def test_table_shows_values_and_unicode() -> None:
    text = run(RECORDS, OutputFormat.TABLE, columns=["key", "summary", "done"])
    assert "DEMO-1" in text
    assert "Änderung" in text
    assert "true" in text


def test_table_does_not_interpret_rich_markup() -> None:
    text = run([{"summary": "[bold red]boom[/bold red]"}], OutputFormat.TABLE)
    assert "[bold red]boom[/bold red]" in text


def test_table_has_no_ansi_codes_when_not_a_tty() -> None:
    assert "\x1b[" not in run(RECORDS, OutputFormat.TABLE)


def test_empty_list_json_is_empty_array() -> None:
    assert json.loads(run([], OutputFormat.JSON)) == []


def test_empty_list_table_and_markdown_write_nothing_to_stdout(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert run([], OutputFormat.TABLE) == ""
    assert run([], OutputFormat.MARKDOWN) == ""
    assert "No results." in capsys.readouterr().err
