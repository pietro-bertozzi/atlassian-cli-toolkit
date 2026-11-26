import base64
import logging
from collections.abc import Callable

import httpx
import pytest

from atlassian_toolkit.core.client import JiraClient, base_url_for, discover_cloud_id
from atlassian_toolkit.core.config import JiraProfile
from atlassian_toolkit.core.errors import ApiError, AuthError, ConfigError, NotFoundError

TOKEN = "fake-token-value"
CLASSIC = JiraProfile(site="example.atlassian.net", email="alice@example.com")
SCOPED = JiraProfile(
    site="example.atlassian.net",
    email="alice@example.com",
    mode="scoped",
    cloud_id="11111111-2222-3333-4444-555555555555",
)

Handler = Callable[[httpx.Request], httpx.Response]


def make_client(
    handler: Handler, profile: JiraProfile = CLASSIC, sleeps: list[float] | None = None
) -> JiraClient:
    recorded = sleeps if sleeps is not None else []
    return JiraClient(
        profile,
        TOKEN,
        transport=httpx.MockTransport(handler),
        sleep=recorded.append,
        jitter=lambda: 1.0,
    )


def sequence(*responses: httpx.Response | Exception) -> tuple[Handler, list[httpx.Request]]:
    """Handler returning the given responses in order; also records the requests."""
    queue = list(responses)
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        item = queue.pop(0)
        if isinstance(item, Exception):
            raise item
        return item

    return handler, seen


def test_base_url_per_mode() -> None:
    assert base_url_for(CLASSIC) == "https://example.atlassian.net"
    assert base_url_for(SCOPED) == (
        "https://api.atlassian.com/ex/jira/11111111-2222-3333-4444-555555555555"
    )


def test_get_sends_basic_auth_and_returns_json() -> None:
    handler, seen = sequence(httpx.Response(200, json={"accountId": "abc"}))
    with make_client(handler) as client:
        assert client.get("/rest/api/3/myself") == {"accountId": "abc"}
    request = seen[0]
    assert str(request.url) == "https://example.atlassian.net/rest/api/3/myself"
    expected = base64.b64encode(f"alice@example.com:{TOKEN}".encode()).decode()
    assert request.headers["Authorization"] == f"Basic {expected}"
    assert request.headers["Accept"] == "application/json"


def test_scoped_mode_uses_gateway_url() -> None:
    handler, seen = sequence(httpx.Response(200, json={}))
    with make_client(handler, SCOPED) as client:
        client.get("/rest/api/3/myself")
    assert str(seen[0].url).startswith("https://api.atlassian.com/ex/jira/1111")


def test_params_are_passed() -> None:
    handler, seen = sequence(httpx.Response(200, json={}))
    with make_client(handler) as client:
        client.get("/rest/api/3/field", params={"x": "1"})
    assert seen[0].url.params["x"] == "1"


def test_401_is_auth_error_mentioning_expiry() -> None:
    handler, _ = sequence(httpx.Response(401))
    with make_client(handler) as client, pytest.raises(AuthError, match="expired or revoked"):
        client.get("/rest/api/3/myself")


def test_403_is_auth_error() -> None:
    handler, _ = sequence(httpx.Response(403, json={"errorMessages": ["No permission"]}))
    with make_client(handler) as client, pytest.raises(AuthError, match="No permission"):
        client.get("/x")


def test_404_is_not_found() -> None:
    handler, _ = sequence(httpx.Response(404, json={"errorMessages": ["Issue does not exist"]}))
    with make_client(handler) as client, pytest.raises(NotFoundError, match="does not exist"):
        client.get("/x")


def test_400_is_api_error_with_detail() -> None:
    handler, _ = sequence(httpx.Response(400, json={"errors": {"jql": "bad query"}}))
    with make_client(handler) as client, pytest.raises(ApiError, match="jql: bad query"):
        client.get("/x")


def test_long_error_detail_is_truncated() -> None:
    handler, _ = sequence(httpx.Response(400, json={"errorMessages": ["x" * 1000]}))
    with make_client(handler) as client, pytest.raises(ApiError) as info:
        client.get("/x")
    assert len(str(info.value)) < 450


def test_invalid_json_is_api_error() -> None:
    handler, _ = sequence(httpx.Response(200, text="<html>"))
    with make_client(handler) as client, pytest.raises(ApiError, match="not valid JSON"):
        client.get("/x")


def test_429_with_retry_after_is_retried() -> None:
    sleeps: list[float] = []
    handler, seen = sequence(
        httpx.Response(429, headers={"Retry-After": "7"}), httpx.Response(200, json={"ok": 1})
    )
    with make_client(handler, sleeps=sleeps) as client:
        assert client.get("/x") == {"ok": 1}
    assert len(seen) == 2
    assert sleeps == [7.0]


def test_429_without_retry_after_is_not_retried() -> None:
    handler, seen = sequence(httpx.Response(429))
    with make_client(handler) as client, pytest.raises(ApiError, match="Rate limited"):
        client.get("/x")
    assert len(seen) == 1


def test_429_with_huge_retry_after_is_not_retried() -> None:
    handler, seen = sequence(httpx.Response(429, headers={"Retry-After": "3600"}))
    with make_client(handler) as client, pytest.raises(ApiError, match="Rate limited"):
        client.get("/x")
    assert len(seen) == 1


def test_503_is_retried_with_exponential_backoff() -> None:
    sleeps: list[float] = []
    handler, seen = sequence(
        httpx.Response(503), httpx.Response(503), httpx.Response(200, json={"ok": 1})
    )
    with make_client(handler, sleeps=sleeps) as client:
        assert client.get("/x") == {"ok": 1}
    assert len(seen) == 3
    assert sleeps == [2.0, 4.0]


def test_retries_are_exhausted() -> None:
    handler, seen = sequence(*[httpx.Response(503)] * 4)
    with make_client(handler) as client, pytest.raises(ApiError, match="HTTP 503"):
        client.get("/x")
    assert len(seen) == 4  # 1 attempt + 3 retries


def test_network_error_is_retried_then_succeeds() -> None:
    handler, seen = sequence(httpx.ConnectError("boom"), httpx.Response(200, json={"ok": 1}))
    with make_client(handler) as client:
        assert client.get("/x") == {"ok": 1}
    assert len(seen) == 2


def test_network_error_exhausted_is_api_error() -> None:
    handler, _ = sequence(*[httpx.ConnectError("boom")] * 4)
    with make_client(handler) as client, pytest.raises(ApiError, match="Network error"):
        client.get("/x")


def test_500_is_not_retried() -> None:
    handler, seen = sequence(httpx.Response(500))
    with make_client(handler) as client, pytest.raises(ApiError, match="HTTP 500"):
        client.get("/x")
    assert len(seen) == 1


def test_token_never_appears_in_logs_or_errors(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.DEBUG, logger="atl.http")
    handler, _ = sequence(httpx.Response(503), httpx.Response(401))
    with make_client(handler) as client, pytest.raises(AuthError) as info:
        client.get("/rest/api/3/myself")
    assert TOKEN not in caplog.text
    assert "Authorization" not in caplog.text
    assert TOKEN not in str(info.value)
    assert caplog.text  # something was logged


# --- writes: retry policy --------------------------------------------------------------------


def test_post_sends_json_and_is_not_retried_on_503() -> None:
    handler, seen = sequence(httpx.Response(503), httpx.Response(201, json={"id": "1"}))
    with make_client(handler) as client, pytest.raises(ApiError, match="may or may not"):
        client.post("/rest/api/3/issue/DEMO-1/comment", {"body": {"type": "doc"}})
    assert len(seen) == 1
    assert seen[0].method == "POST"
    assert seen[0].read() == b'{"body":{"type":"doc"}}'


def test_post_is_not_retried_on_network_error() -> None:
    handler, seen = sequence(httpx.ConnectError("boom"), httpx.Response(201, json={}))
    with make_client(handler) as client, pytest.raises(ApiError, match="check in Jira"):
        client.post("/rest/api/3/issue/DEMO-1/comment", {})
    assert len(seen) == 1


def test_post_is_retried_on_429_with_retry_after() -> None:
    sleeps: list[float] = []
    handler, seen = sequence(
        httpx.Response(429, headers={"Retry-After": "1"}), httpx.Response(201, json={"id": "9"})
    )
    with make_client(handler, sleeps=sleeps) as client:
        assert client.post("/x", {}) == {"id": "9"}
    assert len(seen) == 2


def test_put_is_retried_on_503_and_204_returns_none() -> None:
    handler, seen = sequence(httpx.Response(503), httpx.Response(204))
    with make_client(handler) as client:
        assert client.put("/rest/api/3/issue/DEMO-1/assignee", {"accountId": None}) is None
    assert [r.method for r in seen] == ["PUT", "PUT"]
    assert seen[1].read() == b'{"accountId":null}'


# --- cloud id discovery ----------------------------------------------------------------------

CLOUD_ID = "11111111-2222-3333-4444-555555555555"


def test_discover_cloud_id_reads_tenant_info_without_credentials() -> None:
    handler, seen = sequence(httpx.Response(200, json={"cloudId": CLOUD_ID}))
    assert discover_cloud_id("example.atlassian.net", transport=httpx.MockTransport(handler)) == (
        CLOUD_ID
    )
    assert str(seen[0].url) == "https://example.atlassian.net/_edge/tenant_info"
    assert "Authorization" not in seen[0].headers


@pytest.mark.parametrize(
    "response",
    [
        httpx.Response(404),
        httpx.Response(200, json={"cloudId": "not-a-uuid"}),
        httpx.Response(200, json=["unexpected"]),
        httpx.Response(200, text="<html>"),
    ],
)
def test_discover_cloud_id_failures_point_to_the_docs(response: httpx.Response) -> None:
    handler, _ = sequence(response)
    with pytest.raises(ConfigError, match="--cloud-id"):
        discover_cloud_id("example.atlassian.net", transport=httpx.MockTransport(handler))


def test_discover_cloud_id_network_error() -> None:
    handler, _ = sequence(httpx.ConnectError("boom"))
    with pytest.raises(ConfigError, match="retrieve-my-atlassian-sites-cloud-id"):
        discover_cloud_id("example.atlassian.net", transport=httpx.MockTransport(handler))
