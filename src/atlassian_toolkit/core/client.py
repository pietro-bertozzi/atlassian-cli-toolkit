"""HTTP client for the Jira Cloud REST API.

Responsibilities: base URL per auth mode, Basic auth, timeouts, retries, error mapping.
Nothing outside this module needs to know whether the profile is ``classic`` or ``scoped``.

Retry policy (all requests are idempotent GETs), following Atlassian's rate-limiting guidance
(https://developer.atlassian.com/cloud/jira/platform/rate-limiting/):

* 429 is retried only when the response carries ``Retry-After``.
* 502 / 503 / 504 and network errors are retried with exponential backoff.
* Delay = max(Retry-After, base * 2**attempt) with 0.7-1.3x jitter, capped.

Logging never includes headers, so the ``Authorization`` header cannot leak.
"""

from __future__ import annotations

import logging
import random
import re
import time
from collections.abc import Callable
from types import TracebackType
from typing import Any

import httpx

from atlassian_toolkit import __version__
from atlassian_toolkit.core.config import JiraProfile
from atlassian_toolkit.core.errors import ApiError, AuthError, ConfigError, NotFoundError

logger = logging.getLogger("atl.http")

SCOPED_BASE_URL = "https://api.atlassian.com/ex/jira"
DEFAULT_TIMEOUT = 30.0
DEFAULT_MAX_RETRIES = 3
BASE_DELAY = 2.0
MAX_WAIT = 60.0
RETRYABLE_SERVER_ERRORS = frozenset({502, 503, 504})
MAX_ERROR_DETAIL = 300


def base_url_for(profile: JiraProfile) -> str:
    """Return the API base URL for a profile (the only place that depends on the auth mode)."""
    if profile.mode == "scoped":
        return f"{SCOPED_BASE_URL}/{profile.cloud_id}"
    return f"https://{profile.site}"


class JiraClient:
    """Small synchronous client for Jira Cloud. Use as a context manager."""

    def __init__(
        self,
        profile: JiraProfile,
        token: str,
        *,
        transport: httpx.BaseTransport | None = None,
        timeout: float = DEFAULT_TIMEOUT,
        max_retries: int = DEFAULT_MAX_RETRIES,
        sleep: Callable[[float], None] = time.sleep,
        jitter: Callable[[], float] = lambda: random.uniform(0.7, 1.3),
    ) -> None:
        self._base_url = base_url_for(profile)
        self._max_retries = max_retries
        self._sleep = sleep
        self._jitter = jitter
        self._http = httpx.Client(
            auth=httpx.BasicAuth(profile.email, token),
            headers={"Accept": "application/json", "User-Agent": f"atl/{__version__}"},
            timeout=timeout,
            transport=transport,
        )

    def __enter__(self) -> JiraClient:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self.close()

    def close(self) -> None:
        """Release the underlying connection pool."""
        self._http.close()

    def get(self, path: str, params: dict[str, Any] | None = None) -> Any:
        """GET ``path`` (e.g. ``/rest/api/3/myself``) and return the decoded JSON body."""
        url = f"{self._base_url}{path}"
        for attempt in range(self._max_retries + 1):
            last_attempt = attempt == self._max_retries
            try:
                response = self._http.get(url, params=params)
            except httpx.TransportError as exc:
                if last_attempt:
                    raise ApiError(
                        f"Network error calling Jira ({type(exc).__name__}). "
                        "Check your connection and the site name."
                    ) from exc
                self._backoff(attempt, None, f"network error {type(exc).__name__}")
                continue

            logger.debug("GET %s -> %s", url, response.status_code)
            retry_after = _parse_retry_after(response)
            if not last_attempt and _should_retry(response.status_code, retry_after):
                self._backoff(attempt, retry_after, f"HTTP {response.status_code}")
                continue
            return self._handle(response)
        raise AssertionError("unreachable")  # pragma: no cover

    def _backoff(self, attempt: int, retry_after: float | None, reason: str) -> None:
        delay = max(retry_after or 0.0, BASE_DELAY * 2**attempt) * self._jitter()
        delay = min(delay, MAX_WAIT)
        logger.info("Retrying in %.1fs (%s)", delay, reason)
        self._sleep(delay)

    @staticmethod
    def _handle(response: httpx.Response) -> Any:
        status = response.status_code
        if status == 401:
            raise AuthError(
                "Authentication failed (HTTP 401): the API token may be expired or revoked, "
                "or the email does not match it. Create a new token and run 'atl auth login'."
            )
        if status == 403:
            raise AuthError(
                "Access denied (HTTP 403): the account or token scopes lack permission for "
                f"this resource.{_detail(response)}"
            )
        if status == 404:
            raise NotFoundError(f"Not found (HTTP 404).{_detail(response)}")
        if status == 429:
            raise ApiError("Rate limited by Jira (HTTP 429). Try again later.")
        if status >= 400:
            raise ApiError(f"Jira returned HTTP {status}.{_detail(response)}")
        try:
            return response.json()
        except ValueError as exc:
            raise ApiError("Jira returned a response that is not valid JSON.") from exc


def _should_retry(status: int, retry_after: float | None) -> bool:
    if status == 429:
        return retry_after is not None and retry_after <= MAX_WAIT
    return status in RETRYABLE_SERVER_ERRORS


def _parse_retry_after(response: httpx.Response) -> float | None:
    """Parse ``Retry-After`` given in seconds; HTTP-date values are ignored."""
    value = response.headers.get("Retry-After")
    if value is None:
        return None
    try:
        return max(float(value), 0.0)
    except ValueError:
        return None


def _detail(response: httpx.Response) -> str:
    """Extract Jira's error messages (if any) from an error body, truncated."""
    try:
        body = response.json()
    except ValueError:
        return ""
    if not isinstance(body, dict):
        return ""
    parts: list[str] = [str(m) for m in body.get("errorMessages") or []]
    errors = body.get("errors")
    if isinstance(errors, dict):
        parts.extend(f"{key}: {value}" for key, value in errors.items())
    if not parts:
        return ""
    text = "; ".join(parts)
    if len(text) > MAX_ERROR_DETAIL:
        text = text[:MAX_ERROR_DETAIL] + "..."
    return f" Jira says: {text}"


CLOUD_ID_HELP = "https://support.atlassian.com/jira/kb/retrieve-my-atlassian-sites-cloud-id/"
_UUID = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")


def discover_cloud_id(site: str, *, transport: httpx.BaseTransport | None = None) -> str:
    """Return the site's Cloud ID from ``https://<site>/_edge/tenant_info``.

    Documented by Atlassian (see ``CLOUD_ID_HELP``): a plain GET that returns
    ``{"cloudId": "..."}``. No credentials are sent. Raises ConfigError with a pointer to the
    manual methods when the lookup fails.
    """
    url = f"https://{site}/_edge/tenant_info"
    hint = f"Pass it with --cloud-id; how to find it: {CLOUD_ID_HELP}"
    try:
        with httpx.Client(
            timeout=DEFAULT_TIMEOUT,
            transport=transport,
            headers={"Accept": "application/json", "User-Agent": f"atl/{__version__}"},
        ) as http:
            response = http.get(url)
    except httpx.TransportError as exc:
        raise ConfigError(
            f"Could not look up the Cloud ID of {site} ({type(exc).__name__}). {hint}"
        ) from exc
    logger.debug("GET %s -> %s", url, response.status_code)
    try:
        cloud_id = response.json().get("cloudId") if response.status_code == 200 else None
    except (ValueError, AttributeError):
        cloud_id = None
    if not isinstance(cloud_id, str) or not _UUID.fullmatch(cloud_id):
        raise ConfigError(
            f"Could not find the Cloud ID of {site} (HTTP {response.status_code}). {hint}"
        )
    return cloud_id
