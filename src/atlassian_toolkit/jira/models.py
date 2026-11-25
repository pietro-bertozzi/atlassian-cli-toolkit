"""Data we expose from Jira. JSON key names (the dataclass field names) are a stable contract."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True)
class CurrentUser:
    """The user the API token authenticates as (``GET /rest/api/3/myself``).

    ``email``, ``time_zone`` and ``account_type`` may be None: Jira omits or nulls some fields
    depending on the user's Atlassian Account privacy settings.
    """

    account_id: str
    display_name: str
    email: str | None
    active: bool
    time_zone: str | None
    account_type: str | None

    @classmethod
    def from_api(cls, data: Mapping[str, Any]) -> CurrentUser:
        """Build from the raw ``User`` object returned by the API."""
        return cls(
            account_id=data.get("accountId") or "",
            display_name=data.get("displayName") or "",
            email=data.get("emailAddress") or None,
            active=bool(data.get("active")),
            time_zone=data.get("timeZone") or None,
            account_type=data.get("accountType") or None,
        )

    def to_record(self) -> dict[str, Any]:
        """Return the record rendered by the output layer."""
        return asdict(self)
