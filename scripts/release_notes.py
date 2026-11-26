"""Print the CHANGELOG.md section of one version (used as GitHub release notes).

Usage: python scripts/release_notes.py 0.1.0 [path/to/CHANGELOG.md]
Exits with status 1 if the version has no section, so a release cannot go out without notes.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path


def section(changelog: str, version: str) -> str | None:
    """Return the body of ``## [version] ...`` up to the next ``## `` heading, or None."""
    heading = re.compile(rf"^## \[{re.escape(version)}\][^\n]*\n", re.MULTILINE)
    match = heading.search(changelog)
    if match is None:
        return None
    rest = changelog[match.end() :]
    following = re.search(r"^## ", rest, re.MULTILINE)
    body = rest[: following.start()] if following else rest
    return body.strip() or None


def main(argv: list[str]) -> int:
    if len(argv) not in (2, 3):
        print(__doc__, file=sys.stderr)
        return 2
    path = Path(argv[2]) if len(argv) == 3 else Path("CHANGELOG.md")
    notes = section(path.read_text(encoding="utf-8"), argv[1])
    if notes is None:
        print(f"No non-empty section for version {argv[1]} in {path}.", file=sys.stderr)
        return 1
    print(notes)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
