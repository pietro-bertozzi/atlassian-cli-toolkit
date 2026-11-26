import importlib.util
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "release_notes.py"
_spec = importlib.util.spec_from_file_location("release_notes", SCRIPT)
assert _spec is not None and _spec.loader is not None
release_notes = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(release_notes)

CHANGELOG = """# Changelog

## [Unreleased]

### Added

- Something new.

## [0.2.0] - 2026-12-01

### Added

- Write commands.

## [0.1.0] - 2026-11-27

### Added

- First release.
"""


def test_section_between_headings() -> None:
    assert release_notes.section(CHANGELOG, "0.2.0") == "### Added\n\n- Write commands."


def test_last_section_runs_to_end() -> None:
    assert release_notes.section(CHANGELOG, "0.1.0") == "### Added\n\n- First release."


def test_missing_or_partial_version_is_none() -> None:
    assert release_notes.section(CHANGELOG, "0.3.0") is None
    assert release_notes.section(CHANGELOG, "0.1") is None  # no prefix match


def test_main_fails_without_section(tmp_path: Path) -> None:
    path = tmp_path / "CHANGELOG.md"
    path.write_text(CHANGELOG, encoding="utf-8")
    assert release_notes.main(["x", "9.9.9", str(path)]) == 1
    assert release_notes.main(["x", "0.1.0", str(path)]) == 0
