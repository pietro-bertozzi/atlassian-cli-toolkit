"""``atl auth ...`` commands: create, inspect and remove profiles and their API tokens.

Secrets are never accepted as command-line arguments: the token is read from a hidden prompt,
from stdin (``--token-stdin``) or from a one-off file (``--token-file``, deleted after import),
then stored in the OS keyring. The config file never holds it.
"""

import os
import sys
from pathlib import Path
from typing import Annotated

import typer

from atlassian_toolkit.core.config import (
    PROFILE_ENV_VAR,
    AuthMode,
    JiraProfile,
    default_config_path,
    get_jira_profile,
    load_config,
    normalize_site,
    resolve_profile_name,
    save_config,
)
from atlassian_toolkit.core.context import GlobalOptions
from atlassian_toolkit.core.credentials import (
    JIRA_TOKEN_ENV_VAR,
    delete_jira_token,
    jira_token_source,
    save_jira_token,
)
from atlassian_toolkit.core.errors import ConfigError
from atlassian_toolkit.core.output import echo_err, emit, resolve_format

DEFAULT_PROFILE_NAME = "default"

app = typer.Typer(help="Manage profiles and API tokens.", no_args_is_help=True)


@app.command()
def login(
    ctx: typer.Context,
    site: Annotated[
        str | None, typer.Option("--site", help="Jira site, e.g. example.atlassian.net.")
    ] = None,
    email: Annotated[str | None, typer.Option("--email", help="Atlassian account email.")] = None,
    mode: Annotated[
        AuthMode, typer.Option("--mode", help="'classic' (unscoped token) or 'scoped'.")
    ] = AuthMode.CLASSIC,
    cloud_id: Annotated[
        str | None, typer.Option("--cloud-id", help="Cloud ID of the site (scoped mode only).")
    ] = None,
    token_stdin: Annotated[
        bool, typer.Option("--token-stdin", help="Read the API token from stdin.")
    ] = False,
    token_file: Annotated[
        Path | None,
        typer.Option(
            "--token-file",
            help="Read the API token from this file, store it in the keyring, delete the file.",
        ),
    ] = None,
) -> None:
    """Create or update a profile and store its API token in the OS keyring."""
    options: GlobalOptions = ctx.obj
    if token_stdin and token_file:
        raise ConfigError("Use either --token-stdin or --token-file, not both.")
    if token_stdin and not (site and email):
        raise ConfigError("With --token-stdin, --site and --email are required (no prompting).")
    if mode is AuthMode.SCOPED and not cloud_id and token_stdin:
        raise ConfigError("With --token-stdin and --mode scoped, --cloud-id is required.")

    site = site or typer.prompt("Jira site (e.g. example.atlassian.net)")
    email = email or typer.prompt("Atlassian account email")
    if mode is AuthMode.SCOPED and not cloud_id:
        cloud_id = typer.prompt("Cloud ID")

    profile = JiraProfile(
        site=normalize_site(site), email=email.strip(), mode=mode, cloud_id=cloud_id
    )
    if token_file is not None:
        token_file = token_file.expanduser()  # '~' is not expanded by every shell
        token = _read_token_file(token_file)
    elif token_stdin:
        token = sys.stdin.read()
    else:
        token = typer.prompt("API token", hide_input=True)
    token = token.strip()
    if not token:
        raise ConfigError("The API token is empty. Nothing was saved.")
    if any(char.isspace() for char in token):
        raise ConfigError(
            "The API token contains spaces or line breaks; it must be the token only. "
            "Nothing was saved."
        )

    name = options.profile or os.environ.get(PROFILE_ENV_VAR) or DEFAULT_PROFILE_NAME
    save_jira_token(name, token)  # fails before touching the config if no keyring
    config = load_config()
    config.jira[name] = profile
    config.default_profile = config.default_profile or name
    path = save_config(config)
    echo_err(f"Profile {name!r} saved to {path}. Token stored in the OS keyring.")
    if token_file is not None:
        _delete_token_file(token_file)


def _read_token_file(path: Path) -> str:
    """Return the file's content. ``utf-8-sig`` drops the BOM some Windows editors add."""
    try:
        return path.read_text(encoding="utf-8-sig")
    except FileNotFoundError:
        raise ConfigError(f"Token file not found: {path}") from None
    except (OSError, UnicodeDecodeError) as exc:
        raise ConfigError(f"Cannot read token file {path} ({type(exc).__name__}).") from None


def _delete_token_file(path: Path) -> None:
    """Remove the plaintext copy once the token is safely in the keyring."""
    try:
        path.unlink()
    except OSError as exc:
        echo_err(f"Warning: could not delete {path} ({type(exc).__name__}). Delete it yourself.")
    else:
        echo_err(f"Deleted {path}; the token now lives only in the OS keyring.")


@app.command()
def status(ctx: typer.Context) -> None:
    """Show the selected profile and where its token comes from (never the token)."""
    options: GlobalOptions = ctx.obj
    config = load_config()
    name = resolve_profile_name(options.profile, config)
    profile = get_jira_profile(name, config)
    record = {
        "profile": name,
        "site": profile.site,
        "email": profile.email,
        "mode": str(profile.mode),
        "cloud_id": profile.cloud_id,
        "token_source": jira_token_source(name),
        "config_path": str(default_config_path()),
    }
    emit(record, resolve_format(options.format))


@app.command()
def logout(ctx: typer.Context) -> None:
    """Delete the selected profile and its stored API token."""
    options: GlobalOptions = ctx.obj
    config = load_config()
    name = resolve_profile_name(options.profile, config)
    get_jira_profile(name, config)  # error if unknown

    try:
        delete_jira_token(name)
    except ConfigError as exc:
        echo_err(f"Warning: {exc}")
    del config.jira[name]
    if config.default_profile == name:
        config.default_profile = None
    save_config(config)
    echo_err(f"Profile {name!r} removed.")
    if os.environ.get(JIRA_TOKEN_ENV_VAR):
        echo_err(f"Note: {JIRA_TOKEN_ENV_VAR} is still set in your environment.")
