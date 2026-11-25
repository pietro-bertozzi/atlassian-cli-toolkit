"""Profiles and config file handling.

The config file holds non-secret data only (site, email, auth mode, cloud id). API tokens are
never stored here: see ``credentials.py``.

File layout (TOML), keyed per product so other products can be added later::

    default_profile = "work"

    [profiles.work.jira]
    site = "example.atlassian.net"
    email = "alice@example.com"
    mode = "classic"          # or "scoped"
    cloud_id = "..."          # required when mode = "scoped"
"""

from __future__ import annotations

import os
import tempfile
import tomllib
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Any

import tomli_w
import typer

from atlassian_toolkit.core.errors import ConfigError

APP_NAME = "atl"
CONFIG_FILENAME = "config.toml"
PROFILE_ENV_VAR = "ATL_PROFILE"
CONFIG_DIR_ENV_VAR = "ATL_CONFIG_DIR"


class AuthMode(StrEnum):
    """How the API token is used: classic (site URL) or scoped (api.atlassian.com gateway)."""

    CLASSIC = "classic"
    SCOPED = "scoped"


MODES = tuple(mode.value for mode in AuthMode)


@dataclass(frozen=True)
class JiraProfile:
    """Connection settings for one Jira Cloud site."""

    site: str
    email: str
    mode: str = AuthMode.CLASSIC
    cloud_id: str | None = None

    def __post_init__(self) -> None:
        if self.mode not in MODES:
            raise ConfigError(f"Invalid auth mode {self.mode!r}; expected one of {MODES}.")
        if not self.site or not self.email:
            raise ConfigError("A Jira profile needs both 'site' and 'email'.")
        if self.mode == AuthMode.SCOPED and not self.cloud_id:
            raise ConfigError("Auth mode 'scoped' requires 'cloud_id' in the profile.")


@dataclass
class Config:
    """The whole config file: a default profile name and profiles keyed by name."""

    default_profile: str | None = None
    jira: dict[str, JiraProfile] = field(default_factory=dict)


def default_config_path() -> Path:
    """Return the config file location: ``$ATL_CONFIG_DIR`` or the OS-standard app directory."""
    override = os.environ.get(CONFIG_DIR_ENV_VAR)
    directory = Path(override) if override else Path(typer.get_app_dir(APP_NAME))
    return directory / CONFIG_FILENAME


def normalize_site(site: str) -> str:
    """Reduce ``https://Example.atlassian.net/`` (or a bare host) to ``example.atlassian.net``."""
    host = site.strip()
    for prefix in ("https://", "http://"):
        if host.lower().startswith(prefix):
            host = host[len(prefix) :]
    return host.split("/", 1)[0].lower()


def load_config(path: Path | None = None) -> Config:
    """Load the config file. A missing file yields an empty config."""
    path = path or default_config_path()
    if not path.exists():
        return Config()
    try:
        with path.open("rb") as handle:
            raw = tomllib.load(handle)
    except tomllib.TOMLDecodeError as exc:
        raise ConfigError(f"Config file {path} is not valid TOML: {exc}") from exc
    return _parse(raw, path)


def _parse(raw: dict[str, Any], path: Path) -> Config:
    config = Config(default_profile=raw.get("default_profile"))
    for name, products in raw.get("profiles", {}).items():
        jira = products.get("jira")
        if jira is None:
            continue
        try:
            config.jira[name] = JiraProfile(
                site=jira.get("site", ""),
                email=jira.get("email", ""),
                mode=jira.get("mode", "classic"),
                cloud_id=jira.get("cloud_id"),
            )
        except ConfigError as exc:
            raise ConfigError(f"Profile {name!r} in {path}: {exc}") from exc
    return config


def save_config(config: Config, path: Path | None = None) -> Path:
    """Write the config atomically and return the path used."""
    path = path or default_config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    data: dict[str, Any] = {}
    if config.default_profile:
        data["default_profile"] = config.default_profile
    profiles: dict[str, Any] = {}
    for name, profile in config.jira.items():
        entry = {"site": profile.site, "email": profile.email, "mode": profile.mode}
        if profile.cloud_id:
            entry["cloud_id"] = profile.cloud_id
        profiles[name] = {"jira": entry}
    if profiles:
        data["profiles"] = profiles

    fd, tmp_name = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as handle:
            tomli_w.dump(data, handle)
        os.replace(tmp_name, path)
    except BaseException:
        Path(tmp_name).unlink(missing_ok=True)
        raise
    return path


def resolve_profile_name(explicit: str | None, config: Config) -> str:
    """Pick the profile name: ``--profile`` > ``ATL_PROFILE`` > ``default_profile``."""
    name = explicit or os.environ.get(PROFILE_ENV_VAR) or config.default_profile
    if not name:
        raise ConfigError(
            "No profile selected. Use --profile, set ATL_PROFILE, or run 'atl auth login'."
        )
    return name


def get_jira_profile(name: str, config: Config) -> JiraProfile:
    """Return the Jira profile called ``name`` or raise a ConfigError."""
    try:
        return config.jira[name]
    except KeyError:
        raise ConfigError(
            f"Profile {name!r} has no Jira configuration. Run 'atl auth login'."
        ) from None
