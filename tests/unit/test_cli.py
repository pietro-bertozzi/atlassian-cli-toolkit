"""The root ``atl`` app (global options and wiring)."""

from helpers import runner

from atlassian_toolkit.cli import app


def test_version() -> None:
    result = runner.invoke(app, ["--version"])
    assert result.exit_code == 0
    assert result.stdout.startswith("atl ")
