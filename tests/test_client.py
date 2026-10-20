"""Request building, Idempotency-Keys and error messages of the API client."""

from __future__ import annotations

import pytest
import requests

from prolifik_api.client import (
    API_BASE,
    TIMEOUT,
    USER_AGENT,
    ProlifikClient,
    ProlifikError,
    compact,
    path_id,
)
from prolifik_api.idempotency import KEY_PATTERN, idempotency_key, scope_of

from conftest import API, TEST_KEY, FakeHttp

NOON = 1_792_497_600.0  # 2026-10-20T12:00:00Z
LATER_SAME_HOUR = NOON + 59 * 60
NEXT_HOUR = NOON + 60 * 60


def client(http: FakeHttp | None = None, scope: str | None = "app-1", now: float = NOON) -> ProlifikClient:
    return ProlifikClient(TEST_KEY, scope_id=scope, http=http or FakeHttp(), now=lambda: now)


# --- request building -------------------------------------------------------


def test_get_sends_the_key_only_as_a_bearer_header_to_the_fixed_host() -> None:
    request = client().build_request("GET", "/usage")
    assert API_BASE == API
    assert request["url"] == f"{API}/usage"
    assert request["method"] == "GET"
    assert request["headers"]["Authorization"] == f"Bearer {TEST_KEY}"
    assert request["headers"]["Accept"] == "application/json"
    assert request["headers"]["User-Agent"] == USER_AGENT
    assert "Idempotency-Key" not in request["headers"]
    assert "json" not in request and "params" not in request


def test_key_is_trimmed() -> None:
    request = ProlifikClient(f"  {TEST_KEY}\n", http=FakeHttp()).build_request("GET", "/usage")
    assert request["headers"]["Authorization"] == f"Bearer {TEST_KEY}"


def test_missing_key_is_refused_before_any_request() -> None:
    with pytest.raises(ProlifikError, match="Add your Prolifik API key"):
        ProlifikClient("  ", http=FakeHttp())


def test_get_params_drop_blank_values() -> None:
    request = client().build_request("GET", "/content/pieces", params={"brandId": None, "status": "ready", "before": ""})
    assert request["params"] == {"status": "ready"}


def test_post_sends_compacted_json_and_an_idempotency_key() -> None:
    request = client().build_request(
        "POST", "/clipper/jobs", body={"url": "https://youtu.be/x", "layout": None, "options": {"language": ""}}, dedupe="job"
    )
    assert request["json"] == {"url": "https://youtu.be/x"}
    assert request["headers"]["Content-Type"] == "application/json"
    assert KEY_PATTERN.match(request["headers"]["Idempotency-Key"])
    assert request["headers"]["Idempotency-Key"].startswith("dify:job:")


def test_every_write_must_name_its_dedupe_kind() -> None:
    with pytest.raises(ValueError, match="dedupe"):
        client().build_request("POST", "/clipper/jobs", body={"url": "https://youtu.be/x"})
    with pytest.raises(ValueError, match="idempotency kind"):
        client().build_request("POST", "/clipper/jobs", body={}, dedupe="whatever")


def test_paths_must_be_absolute() -> None:
    with pytest.raises(ValueError):
        client().build_request("GET", "usage")


def test_request_uses_timeout_and_never_follows_redirects() -> None:
    http = FakeHttp().queue(200, {"plan": "pro"})
    assert client(http).get("/usage") == {"plan": "pro"}
    assert http.calls[0]["timeout"] == TIMEOUT
    assert http.calls[0]["allow_redirects"] is False


def test_compact_keeps_list_positions_for_custom_texts() -> None:
    body = {"customTexts": [{"text": "one"}, None, {"text": "three"}], "empty": {}, "blank": "  "}
    assert compact(body) == {"customTexts": [{"text": "one"}, None, {"text": "three"}]}


@pytest.mark.parametrize("value", ["3f9c2a7be41d", "e1f2a3b4-c5d6-4e7f-8a9b-0c1d2e3f4a5b"])
def test_path_id_accepts_prolifik_ids(value: str) -> None:
    assert path_id(value, "Job ID") == value


@pytest.mark.parametrize("value", ["../usage", "a/b", "id?x=1", "", None, "x" * 129, "id%2F"])
def test_path_id_refuses_anything_that_could_change_the_path(value: object) -> None:
    with pytest.raises(ProlifikError, match="must be a Prolifik ID"):
        path_id(value, "Job ID")


# --- Idempotency-Keys (same conventions as integrations/zapier/lib/idempotency.js) ---


def key_of(c: ProlifikClient, body: dict, dedupe: str = "job", path: str = "/content/jobs") -> str:
    return c.build_request("POST", path, body=body, dedupe=dedupe)["headers"]["Idempotency-Key"]


def test_job_key_repeats_for_a_retry_in_the_same_scope_and_hour() -> None:
    body = {"brandId": "b", "format": "kinetic-type", "count": 2}
    assert key_of(client(now=NOON), body) == key_of(client(now=LATER_SAME_HOUR), body)


def test_job_key_ignores_key_order_and_blank_fields() -> None:
    a = {"brandId": "b", "format": "kinetic-type", "count": 2}
    b = {"count": 2, "format": "kinetic-type", "brandId": "b", "contentSourceId": None}
    assert key_of(client(), a) == key_of(client(), b)


def test_job_key_changes_with_the_hour_the_scope_the_body_and_the_path() -> None:
    body = {"brandId": "b", "format": "kinetic-type"}
    base = key_of(client(), body)
    assert key_of(client(now=NEXT_HOUR), body) != base
    assert key_of(client(scope="app-2"), body) != base
    assert key_of(client(), {**body, "count": 3}) != base
    assert key_of(client(), body, path="/content/sources") != base


def test_job_key_is_random_without_a_scope() -> None:
    body = {"brandId": "b"}
    first, second = key_of(client(scope=None), body), key_of(client(scope=None), body)
    assert first != second
    assert KEY_PATTERN.match(first)


def test_post_key_ignores_scope_and_hour() -> None:
    body = {"connectionIds": ["c1"], "caption": "hi"}
    path = "/content/pieces/p1/publish"
    assert key_of(client(scope="a", now=NOON), body, "post", path) == key_of(client(scope="b", now=NEXT_HOUR), body, "post", path)


def test_key_format_matches_what_the_api_accepts() -> None:
    key = idempotency_key(kind="job", method="post", path="/x", body={"a": "ü"}, scope_id="s", now=NOON)
    assert KEY_PATTERN.match(key) and len(key) <= 128


def test_scope_is_the_app_plus_the_chat_message() -> None:
    class Session:
        app_id = "app-9"
        message_id = "msg-3"

    assert scope_of(Session()) == "app-9:msg-3"
    Session.message_id = None
    assert scope_of(Session()) == "app-9"
    Session.app_id = None
    assert scope_of(Session()) is None
    assert scope_of(None) is None


# --- errors -----------------------------------------------------------------


def error_of(status: int, body: object = None, headers: dict | None = None) -> ProlifikError:
    http = FakeHttp().queue(status, body, headers)
    with pytest.raises(ProlifikError) as caught:
        client(http).get("/usage")
    return caught.value


def test_401_says_how_to_get_a_new_key_and_never_echoes_it() -> None:
    error = error_of(401, {"error": {"code": "invalid_api_key", "message": "invalid_api_key"}})
    assert "invalid, expired or revoked" in str(error)
    assert "Settings > Developer API" in str(error)
    assert TEST_KEY not in str(error)
    assert error.status == 401


def test_403_insufficient_scope_lists_the_scopes() -> None:
    error = error_of(403, {"error": {"code": "insufficient_scope", "message": "This key lacks clipper:write"}})
    assert str(error).startswith("This key lacks clipper:write.")
    assert "content:read, content:write, clipper:read, clipper:write" in str(error)


def test_402_adds_the_upgrade_link() -> None:
    error = error_of(402, {"error": {"code": "render_budget", "message": "No renders left this month", "upgradeUrl": "https://app.getprolifik.com/pricing?x=1"}})
    assert str(error) == "No renders left this month. Plans and limits: https://app.getprolifik.com/pricing?x=1"


def test_402_ignores_a_non_https_upgrade_link() -> None:
    error = error_of(402, {"error": {"message": "Upgrade", "upgradeUrl": "javascript:alert(1)"}})
    assert str(error).endswith("https://app.getprolifik.com/pricing")


def test_429_carries_retry_after() -> None:
    error = error_of(429, {"error": {"message": "Too many clip jobs this hour"}}, {"Retry-After": "120"})
    assert str(error) == "Too many clip jobs this hour. Try again in 120 seconds."
    assert error.retry_after == 120


def test_409_in_flight_says_to_run_again() -> None:
    error = error_of(409, {"error": {"message": "Request in progress"}}, {"Retry-After": "2"})
    assert "Run the step again in 2 seconds" in str(error)


def test_409_without_retry_after_is_the_api_message() -> None:
    error = error_of(409, {"error": {"message": "Content source is not ready yet."}})
    assert str(error) == "Content source is not ready yet."


def test_500_adds_the_request_id() -> None:
    error = error_of(502, {"error": {"requestId": "req_123"}})
    assert "HTTP 502" in str(error) and "Request ID: req_123." in str(error)


def test_non_json_error_body_still_gives_a_message() -> None:
    error = error_of(400, b"<html>bad</html>")
    assert str(error) == "Prolifik rejected the request (HTTP 400)."


def test_redirect_is_an_error_not_followed() -> None:
    error = error_of(302, None, {"Location": "https://elsewhere.example"})
    assert "HTTP 302" in str(error)


def test_timeout_and_connection_errors_are_readable() -> None:
    with pytest.raises(ProlifikError, match="did not answer within 60 seconds"):
        client(FakeHttp().fail_with(requests.exceptions.ReadTimeout("x"))).get("/usage")
    with pytest.raises(ProlifikError, match="Could not reach Prolifik"):
        client(FakeHttp().fail_with(requests.exceptions.ConnectionError("x"))).get("/usage")


def test_non_json_success_is_an_error() -> None:
    with pytest.raises(ProlifikError, match="not JSON"):
        client(FakeHttp().queue(200, b"<html>")).get("/usage")
