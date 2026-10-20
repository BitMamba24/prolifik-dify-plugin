"""Idempotency-Key derivation, kept in step with the Zapier integration.

The API requires an Idempotency-Key on every create and keeps each key's
response for 24 hours per API key; a key reused with different data is refused
with 409 (src/lib/public-api/idempotency.ts). integrations/zapier/lib/idempotency.js
sets the conventions this module follows:

- 'post' (public posts): a hash of the request alone. The same item to the same
  accounts, caption and time is the same post from any run, so a repeat within
  24 hours gets the first post back instead of posting twice. No tool in this
  plugin publishes yet; the kind is here so one that does cannot skip it.
- 'job' (anything that queues work: clips, videos, content sources): a hash of
  the request, the Dify scope and the UTC hour. Zapier scopes by Zap ID; the
  Dify equivalent is the app ID, plus the chat message ID when there is one.
  A retry of the same step (Dify's retry-on-failure, or an agent re-calling the
  tool inside one turn) repeats the request in the same scope and hour and gets
  the first job back. A new chat message is a new request, so asking for "3
  more" in the next turn makes a new batch. A workflow run has no message ID,
  so, as on Zapier, two runs of one app with identical inputs inside one UTC
  hour get one job, and a retry that crosses the hour can create a second one.
  With no app ID at all the key is random, so two apps never share a job.
"""

from __future__ import annotations

import hashlib
import json
import re
import time
import uuid
from typing import Any

# What the API accepts.
KEY_PATTERN = re.compile(r"^[A-Za-z0-9._:-]{8,128}$")

KINDS = frozenset({"post", "job"})
PREFIX = "dify"


def canonical(value: Any) -> Any:
    """The value with dict keys sorted, so equal requests hash equally."""
    if isinstance(value, list):
        return [canonical(entry) for entry in value]
    if isinstance(value, dict):
        return {key: canonical(value[key]) for key in sorted(value)}
    return value


def utc_hour(now: float) -> str:
    """The UTC hour of a Unix timestamp, e.g. 2026-10-20T14."""
    return time.strftime("%Y-%m-%dT%H", time.gmtime(now))


def idempotency_key(
    *,
    kind: str,
    method: str,
    path: str,
    body: Any,
    scope_id: str | None,
    now: float | None = None,
) -> str:
    if kind not in KINDS:
        raise ValueError(f"Every write needs an idempotency kind, got {kind!r}.")
    if kind == "job" and not scope_id:
        return f"{PREFIX}:job:{uuid.uuid4().hex}"
    scope: list[str] = []
    if kind == "job":
        scope = [str(scope_id), utc_hour(time.time() if now is None else now)]
    payload = json.dumps(
        [method.upper(), path, canonical(body or {}), *scope],
        separators=(",", ":"),
        ensure_ascii=False,
    )
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    return f"{PREFIX}:{kind}:{digest}"


def scope_of(session: Any) -> str | None:
    """The Dify app, plus the chat message when the call comes from a chat turn."""
    app_id = getattr(session, "app_id", None) if session is not None else None
    if not app_id:
        return None
    message_id = getattr(session, "message_id", None)
    return f"{app_id}:{message_id}" if message_id else str(app_id)
