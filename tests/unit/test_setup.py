from pathlib import Path

from typer.testing import CliRunner

from atlassian_toolkit.cli import app
from atlassian_toolkit.setup_commands import skill_text

runner = CliRunner()


def test_packaged_skill_has_frontmatter() -> None:
    text = skill_text()
    assert text.startswith("---\nname: atl-jira\n")
    assert "description:" in text


def test_claude_skill_installs_then_is_idempotent(tmp_path: Path) -> None:
    args = ["setup", "claude-skill", "--skills-dir", str(tmp_path)]
    result = runner.invoke(app, args)
    assert result.exit_code == 0, result.output
    target = tmp_path / "atl-jira" / "SKILL.md"
    assert target.read_text(encoding="utf-8") == skill_text()
    again = runner.invoke(app, args)
    assert again.exit_code == 0
    assert "Already up to date" in again.stderr


def test_claude_skill_refuses_to_overwrite_without_force(tmp_path: Path) -> None:
    target = tmp_path / "atl-jira" / "SKILL.md"
    target.parent.mkdir(parents=True)
    target.write_text("my own edits", encoding="utf-8")
    args = ["setup", "claude-skill", "--skills-dir", str(tmp_path)]
    result = runner.invoke(app, args)
    assert result.exit_code == 3
    assert "--force" in result.stderr
    assert target.read_text(encoding="utf-8") == "my own edits"
    forced = runner.invoke(app, [*args, "--force"])
    assert forced.exit_code == 0, forced.output
    assert target.read_text(encoding="utf-8") == skill_text()
