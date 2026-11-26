"""Open a Jira client for the selected profile (used by ``atl jira`` and ``atl auth``).

The one place that turns a profile name into a ready client: config -> profile -> token ->
client. Errors keep their exit codes (3 unknown profile or missing token).
"""

from atlassian_toolkit.core.client import JiraClient
from atlassian_toolkit.core.config import (
    JiraProfile,
    get_jira_profile,
    load_config,
    resolve_profile_name,
)
from atlassian_toolkit.core.credentials import get_jira_token


def selected_profile(explicit: str | None) -> tuple[str, JiraProfile]:
    """Return ``(name, profile)`` for ``--profile`` > ``ATL_PROFILE`` > ``default_profile``."""
    config = load_config()
    name = resolve_profile_name(explicit, config)
    return name, get_jira_profile(name, config)


def open_client(name: str, profile: JiraProfile) -> JiraClient:
    """A client for ``profile`` authenticated with the token stored for ``name``."""
    return JiraClient(profile, get_jira_token(name))
