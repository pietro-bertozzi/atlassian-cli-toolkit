# Releases

A **release** is a named, frozen version of the toolkit (e.g. `v0.1.0`) that other projects
install. Day-to-day work happens on `main`; a release marks a commit on `main` as "this is
version X" so you can install exactly that and upgrade on purpose.

## Versions

[Semantic versioning](https://semver.org/) `MAJOR.MINOR.PATCH`, while pre-1.0:

- new commands or options → bump **MINOR** (`0.1.0` → `0.2.0`);
- bug fixes only → bump **PATCH** (`0.2.0` → `0.2.1`);
- a breaking change (e.g. a renamed JSON key) is called out in the changelog.

The version lives in one place: `__version__` in `src/atlassian_toolkit/__init__.py`
(`pyproject.toml` reads it from there).

## Making a release

1. Make sure CI is green on `main`.
2. In `CHANGELOG.md`, rename `## [Unreleased]` to `## [X.Y.Z] - YYYY-MM-DD` and add a new
   empty `## [Unreleased]` above it.
3. Set `__version__ = "X.Y.Z"` in `src/atlassian_toolkit/__init__.py`.
4. Commit: `chore: release X.Y.Z`, push.
5. Tag and push the tag:

   ```bash
   git tag vX.Y.Z
   git push origin vX.Y.Z
   ```

The `Release` workflow (`.github/workflows/release.yml`) then runs the tests, checks that the
tag matches `__version__`, builds the wheel and sdist, and creates a GitHub release with the
changelog section as notes. If any step fails, no release is created: fix, delete the tag
(`git tag -d vX.Y.Z` and `git push origin :refs/tags/vX.Y.Z`) and tag again.

Releases are not published to PyPI.

## Installing a release (any project, any OS)

```bash
uv tool install git+https://github.com/pietro-bertozzi/atlassian-cli-toolkit@v0.1.0
atl --version
```

`uv tool install` puts `atl` on your `PATH` in its own isolated environment, so it works in
every project and does not touch project dependencies. To move to another release:

```bash
uv tool install --force git+https://github.com/pietro-bertozzi/atlassian-cli-toolkit@v0.2.0
```

Your login (config file and keyring entry) is per machine and survives upgrades.

To run your local working copy everywhere instead (while developing the toolkit):
`uv tool install --force --editable <path-to>/atlassian-cli-toolkit`.
