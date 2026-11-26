"""``atl setup ...``: one-time helpers for using ``atl`` from coding agents.

The Claude Code skill shipped with the package (``skills/atl-jira/SKILL.md``) is the single
source of truth; ``atl setup claude-skill`` copies it to the user-level skills directory so
Claude Code knows how to use ``atl`` in every project.
"""

from importlib import resources
from pathlib import Path
from typing import Annotated

import typer

from atlassian_toolkit.core.errors import ConfigError
from atlassian_toolkit.core.output import echo_err

SKILL_NAME = "atl-jira"

app = typer.Typer(help="One-time setup helpers (e.g. the Claude Code skill).", no_args_is_help=True)


def skill_text() -> str:
    """Return the packaged ``SKILL.md``."""
    skill = resources.files("atlassian_toolkit").joinpath("skills").joinpath(SKILL_NAME)
    return skill.joinpath("SKILL.md").read_text(encoding="utf-8")


def default_skills_dir() -> Path:
    """User-level Claude Code skills directory: ``~/.claude/skills`` (applies to all projects)."""
    return Path.home() / ".claude" / "skills"


@app.command("claude-skill")
def claude_skill(
    skills_dir: Annotated[
        Path | None,
        typer.Option("--skills-dir", help="Skills directory (default: ~/.claude/skills)."),
    ] = None,
    force: Annotated[
        bool, typer.Option("--force", help="Replace an existing, different SKILL.md.")
    ] = False,
) -> None:
    """Install the atl-jira skill so Claude Code uses atl in all your projects."""
    target = (skills_dir or default_skills_dir()).expanduser() / SKILL_NAME / "SKILL.md"
    text = skill_text()
    try:
        if target.exists():
            if target.read_text(encoding="utf-8", errors="replace") == text:
                echo_err(f"Already up to date: {target}")
                return
            if not force:
                raise ConfigError(
                    f"{target} already exists and differs (edited, or from another atl "
                    "version). Re-run with --force to replace it."
                )
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")
    except OSError as exc:
        raise ConfigError(f"Cannot write {target} ({type(exc).__name__}).") from None
    echo_err(f"Installed the {SKILL_NAME} skill to {target}. New Claude Code sessions will use it.")
