"""HTTP client for the Prolifik public REST API.

Every request goes to the fixed API_BASE host. Path segments that carry IDs
are checked before they are joined into the URL, redirects are not followed,
and the API key only ever travels in the Authorization header to that host.
Error messages are written here from the API's own message and never echo the
key.
"""

from __future__ import annotations

import re
import time
from typing import Any, Callable
from urllib.parse import quote

import requests

from .idempotency import idempotency_key

PLUGIN_VERSION = "0.1.0"

API_BASE = "https://app.getprolifik.com/api/v1"
KEY_SETTINGS_URL = "https://app.getprolifik.com/home?settings=developer"
PRICING_URL = "https://app.getprolifik.com/pricing"
USER_AGENT = f"prolifik-dify-plugin/{PLUGIN_VERSION}"

# Every scope a tool in this plugin can touch.
REQUIRED_SCOPES = ("content:read", "content:write", "clipper:read", "clipper:write")

# (connect, read) seconds. Creates answer in a second or two; the slowest read
# is a clip job, which presigns every clip URL.
TIMEOUT = (10, 60)

# Tests swap this for a recorder; nothing else should.
http_factory: Callable[[], Any] = requests.Session

ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]{1,128}$")
MACHINE_CODE = re.compile(r"^[a-z0-9_]+$")


class ProlifikError(Exception):
    """An error a Dify user can act on. str(error) is the whole message."""

    def __init__(
        self,
        message: str,
        *,
        status: int | None = None,
        code: str | None = None,
        retry_after: int | None = None,
    ) -> None:
        super().__init__(message)
        self.status = status
        self.code = code
        self.retry_after = retry_after


def is_blank(value: Any) -> bool:
    return (
        value is None
        or (isinstance(value, str) and value.strip() == "")
        or (isinstance(value, (list, tuple)) and len(value) == 0)
    )


def compact(value: Any) -> Any:
    """Drop blank values recursively so optional inputs never reach the API as
    empty strings. Lists keep every entry and position: the API reads
    customTexts by index, where None means "the AI writes this video"."""
    if isinstance(value, list):
        return [compact(entry) for entry in value]
    if isinstance(value, dict):
        out: dict[str, Any] = {}
        for key, entry in value.items():
            entry = compact(entry)
            if is_blank(entry) or (isinstance(entry, dict) and not entry):
                continue
            out[key] = entry
        return out
    return value


def path_id(value: Any, label: str) -> str:
    """An ID safe to put in a URL path, or a ProlifikError."""
    text = str(value).strip() if value is not None else ""
    if not ID_PATTERN.match(text):
        raise ProlifikError(f"{label} must be a Prolifik ID (letters, numbers, - and _), got {text[:80]!r}.")
    return quote(text, safe="")


def _with_period(text: str) -> str:
    return text if re.search(r"[.!?]$", text) else f"{text}."


def _retry_after(response: Any) -> int | None:
    try:
        return int(response.headers.get("retry-after"))
    except (TypeError, ValueError):
        return None


def error_for(response: Any) -> ProlifikError:
    """Turn an API error response into a message a Dify user can act on."""
    status = response.status_code
    try:
        body = response.json()
    except ValueError:
        body = {}
    error = body.get("error") if isinstance(body, dict) else None
    error = error if isinstance(error, dict) else {}
    raw_message = error.get("message") if isinstance(error.get("message"), str) else ""
    raw_message = raw_message.strip()
    api_message = "" if not raw_message or MACHINE_CODE.match(raw_message) else raw_message
    code = error.get("code") if isinstance(error.get("code"), str) else None
    retry_after = _retry_after(response)

    if status == 401:
        message = (
            "Your Prolifik API key is invalid, expired or revoked. Create a new key in Prolifik under "
            f"Settings > Developer API ({KEY_SETTINGS_URL}) and update the Prolifik credentials in Dify."
        )
    elif status == 403 and code == "insufficient_scope":
        message = (
            f"{_with_period(api_message or 'This API key is missing a scope this tool needs')} "
            f"Create a key with the {', '.join(REQUIRED_SCOPES)} scopes under Settings > Developer API "
            "in Prolifik, then update the Prolifik credentials in Dify."
        )
    elif status == 403:
        message = _with_period(api_message or "Your Prolifik account does not have access to this")
    elif status == 402:
        upgrade = error.get("upgradeUrl")
        upgrade = upgrade if isinstance(upgrade, str) and upgrade.startswith("https://") else PRICING_URL
        message = (
            f"{_with_period(api_message or 'Your Prolifik plan does not include this, or its monthly allowance is used up')} "
            f"Plans and limits: {upgrade}"
        )
    elif status == 429:
        wait = f" Try again in {retry_after} seconds." if retry_after is not None else " Try again shortly."
        message = _with_period(api_message or "Prolifik is rate limiting requests") + wait
    elif status == 409 and retry_after is not None:
        # The same Idempotency-Key is still in flight: a retry arrived before the
        # first try answered. Running the step again later returns that result.
        message = (
            _with_period(api_message or "Prolifik is still processing this request")
            + f" Run the step again in {retry_after} seconds to get its result."
        )
    elif status == 404:
        message = _with_period(api_message or "Prolifik could not find that item. It may have been deleted")
    elif status >= 500:
        request_id = error.get("requestId")
        suffix = f" Request ID: {request_id}." if isinstance(request_id, str) and request_id else ""
        message = (
            _with_period(api_message or f"Prolifik is having trouble right now (HTTP {status}). Try again in a few minutes")
            + suffix
        )
    else:
        message = _with_period(api_message or f"Prolifik rejected the request (HTTP {status})")

    return ProlifikError(message, status=status, code=code, retry_after=retry_after)


class ProlifikClient:
    """One API key, one Dify scope (for Idempotency-Keys)."""

    def __init__(
        self,
        api_key: str,
        *,
        scope_id: str | None = None,
        http: Any = None,
        now: Callable[[], float] = time.time,
    ) -> None:
        key = str(api_key or "").strip()
        if not key:
            raise ProlifikError(
                f"Add your Prolifik API key to the Prolifik credentials in Dify. Create one under Settings > Developer API ({KEY_SETTINGS_URL})."
            )
        self._api_key = key
        self._scope_id = scope_id
        self._http = http if http is not None else http_factory()
        self._now = now

    def build_request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        body: dict[str, Any] | None = None,
        dedupe: str | None = None,
    ) -> dict[str, Any]:
        """The keyword arguments for requests.Session.request, without sending."""
        if not path.startswith("/"):
            raise ValueError(f"API paths start with '/', got {path!r}.")
        method = method.upper()
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Accept": "application/json",
            "User-Agent": USER_AGENT,
        }
        request: dict[str, Any] = {"method": method, "url": f"{API_BASE}{path}", "headers": headers}
        if params:
            cleaned = compact(params)
            if cleaned:
                request["params"] = cleaned
        if method != "GET":
            if dedupe is None:
                raise ValueError("Every write says how a repeat is recognised: pass dedupe='job' or 'post'.")
            sent = compact(body or {})
            request["json"] = sent
            headers["Content-Type"] = "application/json"
            headers["Idempotency-Key"] = idempotency_key(
                kind=dedupe, method=method, path=path, body=sent, scope_id=self._scope_id, now=self._now()
            )
        return request

    def request(self, method: str, path: str, **kwargs: Any) -> dict[str, Any]:
        prepared = self.build_request(method, path, **kwargs)
        try:
            response = self._http.request(**prepared, timeout=TIMEOUT, allow_redirects=False)
        except requests.exceptions.Timeout as err:
            raise ProlifikError(
                f"Prolifik did not answer within {TIMEOUT[1]} seconds. Try again in a minute."
            ) from err
        except requests.exceptions.RequestException as err:
            raise ProlifikError(
                "Could not reach Prolifik at app.getprolifik.com. Check that this Dify instance can make outbound HTTPS requests."
            ) from err
        if response.status_code >= 300:
            raise error_for(response)
        if response.status_code == 204 or not response.content:
            return {}
        try:
            data = response.json()
        except ValueError as err:
            raise ProlifikError(f"Prolifik sent a response that is not JSON (HTTP {response.status_code}).") from err
        return data if isinstance(data, dict) else {"data": data}

    def get(self, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        return self.request("GET", path, params=params)

    def post(self, path: str, body: dict[str, Any], *, dedupe: str) -> dict[str, Any]:
        return self.request("POST", path, body=body, dedupe=dedupe)
