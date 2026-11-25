from pathlib import Path

import pytest

from atlassian_toolkit.core.config import (
    Config,
    JiraProfile,
    get_jira_profile,
    load_config,
    resolve_profile_name,
    save_config,
)
from atlassian_toolkit.core.errors import ConfigError


def make_config() -> Config:
    return Config(
        default_profile="work",
        jira={
            "work": JiraProfile(site="example.atlassian.net", email="alice@example.com"),
            "scoped": JiraProfile(
                site="example.atlassian.net",
                email="alice@example.com",
                mode="scoped",
                cloud_id="00000000-0000-0000-0000-000000000000",
            ),
        },
    )


def test_missing_file_gives_empty_config(tmp_path: Path) -> None:
    config = load_config(tmp_path / "nope.toml")
    assert config.default_profile is None
    assert config.jira == {}


def test_save_then_load_roundtrip(tmp_path: Path) -> None:
    path = tmp_path / "sub" / "config.toml"
    save_config(make_config(), path)
    assert load_config(path) == make_config()


def test_saved_file_contains_no_token_field(tmp_path: Path) -> None:
    path = save_config(make_config(), tmp_path / "config.toml")
    assert "token" not in path.read_text().lower()


def test_invalid_toml_raises_config_error(tmp_path: Path) -> None:
    path = tmp_path / "config.toml"
    path.write_text("not = [valid")
    with pytest.raises(ConfigError):
        load_config(path)


def test_scoped_mode_requires_cloud_id() -> None:
    with pytest.raises(ConfigError, match="cloud_id"):
        JiraProfile(site="example.atlassian.net", email="alice@example.com", mode="scoped")


def test_unknown_mode_rejected() -> None:
    with pytest.raises(ConfigError, match="mode"):
        JiraProfile(site="example.atlassian.net", email="alice@example.com", mode="bogus")


def test_invalid_profile_in_file_names_the_profile(tmp_path: Path) -> None:
    path = tmp_path / "config.toml"
    path.write_text('[profiles.broken.jira]\nsite = "example.atlassian.net"\n')
    with pytest.raises(ConfigError, match="broken"):
        load_config(path)


def test_profile_resolution_order(monkeypatch: pytest.MonkeyPatch) -> None:
    config = Config(default_profile="from-config")
    monkeypatch.delenv("ATL_PROFILE", raising=False)
    assert resolve_profile_name(None, config) == "from-config"
    monkeypatch.setenv("ATL_PROFILE", "from-env")
    assert resolve_profile_name(None, config) == "from-env"
    assert resolve_profile_name("explicit", config) == "explicit"


def test_no_profile_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ATL_PROFILE", raising=False)
    with pytest.raises(ConfigError):
        resolve_profile_name(None, Config())


def test_get_jira_profile_unknown_raises() -> None:
    with pytest.raises(ConfigError, match="missing"):
        get_jira_profile("missing", make_config())
