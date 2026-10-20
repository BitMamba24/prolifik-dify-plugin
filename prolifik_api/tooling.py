"""Helpers every tool shares: the client for the tool's credentials, input
parsing, and emitting results.

Tool modules import functions from here, never a Tool subclass: the Dify SDK
loads a tool by finding exactly one Tool subclass in its module, so a second
one imported by name breaks loading (tests/test_definitions.py checks this).
"""

from __future__ import annotations

from collections.abc import Generator, Iterable
from typing import Any

from .client import ProlifikClient, ProlifikError, is_blank
from .idempotency import scope_of

CREDENTIAL_KEY = "api_key"


def client_for(tool: Any) -> ProlifikClient:
    settings = getattr(tool.runtime, "credentials", None) or {}
    client = ProlifikClient(settings.get(CREDENTIAL_KEY, ""), scope_id=scope_of(getattr(tool, "session", None)))
    return client


def trimmed(value: Any) -> str | None:
    return None if is_blank(value) else str(value).strip()


def to_int(value: Any, label: str, *, minimum: int, maximum: int) -> int | None:
    """A whole number within bounds, or None when blank."""
    if is_blank(value):
        return None
    try:
        number = float(str(value).strip())
    except ValueError as err:
        raise ProlifikError(f"{label} must be a whole number, got {str(value)[:40]!r}.") from err
    if not number.is_integer():
        raise ProlifikError(f"{label} must be a whole number, got {value}.")
    whole = int(number)
    if whole < minimum or whole > maximum:
        raise ProlifikError(f"{label} must be from {minimum} to {maximum}, got {whole}.")
    return whole


def to_bool(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    if is_blank(value):
        return None
    text = str(value).strip().lower()
    if text in {"true", "yes", "1", "on"}:
        return True
    if text in {"false", "no", "0", "off"}:
        return False
    return None


def choice(value: Any, allowed: Iterable[str], label: str) -> str | None:
    """A select value, checked here because an agent can send any string."""
    text = trimmed(value)
    if text is None:
        return None
    options = list(allowed)
    if text not in options:
        raise ProlifikError(f"{label} must be one of {', '.join(options)}, got {text[:40]!r}.")
    return text


def resolve_brand_id(client: ProlifikClient, value: Any) -> str:
    """The brand ID given, else the account's active brand, else its first brand."""
    given = trimmed(value)
    if given:
        return given
    data = client.get("/brands")
    brands = [brand for brand in data.get("brands") or [] if isinstance(brand, dict) and brand.get("id")]
    active = data.get("activeBrandId")
    for brand in brands:
        if brand.get("id") == active:
            return str(brand["id"])
    if brands:
        return str(brands[0]["id"])
    raise ProlifikError(
        "This Prolifik account has no brand yet. Add one at https://app.getprolifik.com, then run the tool again."
    )


def emit(tool: Any, result: dict[str, Any], text: str, variables: Iterable[str]) -> Generator[Any, None, None]:
    """A short summary for agents, the whole result as JSON, and one workflow
    variable per name in the tool's output_schema."""
    yield tool.create_text_message(text)
    yield tool.create_json_message(result)
    for name in variables:
        yield tool.create_variable_message(name, result.get(name))
