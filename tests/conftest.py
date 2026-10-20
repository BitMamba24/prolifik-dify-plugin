"""Shared fixtures. No test here reaches the network: every request goes to
FakeHttp, which records it and answers from a queue. tests/test_live.py is the
one exception and runs only when PROLIFIK_TEST_API_KEY is set."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from requests.structures import CaseInsensitiveDict

from dify_plugin.entities.tool import ToolRuntime
from prolifik_api import client as client_module

ROOT = Path(__file__).resolve().parents[1]
API = "https://app.getprolifik.com/api/v1"
TEST_KEY = "plk_live_unit_test_key_0000000000"


class FakeResponse:
    def __init__(self, status: int = 200, body: Any = None, headers: dict[str, str] | None = None) -> None:
        self.status_code = status
        self.headers = CaseInsensitiveDict(headers or {})
        self.content = b"" if body is None else (body if isinstance(body, bytes) else json.dumps(body).encode())

    def json(self) -> Any:
        return json.loads(self.content)


class FakeHttp:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []
        self.responses: list[Any] = []

    def queue(self, status: int = 200, body: Any = None, headers: dict[str, str] | None = None) -> "FakeHttp":
        self.responses.append(FakeResponse(status, body, headers))
        return self

    def fail_with(self, error: Exception) -> "FakeHttp":
        self.responses.append(error)
        return self

    def request(self, **kwargs: Any) -> FakeResponse:
        self.calls.append(kwargs)
        if not self.responses:
            raise AssertionError(f"Unexpected request: {kwargs['method']} {kwargs['url']}")
        answer = self.responses.pop(0)
        if isinstance(answer, Exception):
            raise answer
        return answer


@pytest.fixture
def http(monkeypatch: pytest.MonkeyPatch) -> FakeHttp:
    fake = FakeHttp()
    monkeypatch.setattr(client_module, "http_factory", lambda: fake)
    return fake


_CLASSES: dict[str, type] = {}


def tool_class(name: str) -> type:
    """The tool's class, found the way the Dify runtime finds it (exactly one
    Tool subclass in the module, or the runtime refuses to load it)."""
    if name not in _CLASSES:
        from dify_plugin import Tool
        from dify_plugin.core.utils.class_loader import load_single_subclass_from_source

        _CLASSES[name] = load_single_subclass_from_source(
            module_name=f"tools.{name}", script_path=str(ROOT / "tools" / f"{name}.py"), parent_type=Tool
        )
    return _CLASSES[name]


def tool_globals(name: str) -> dict[str, Any]:
    """The globals of the module the loaded tool class runs in, for
    monkeypatch.setitem (the loader may build a module that is not the one in
    sys.modules)."""
    return tool_class(name)._invoke.__globals__


def make_tool(name: str, *, app_id: str | None = "app-1", message_id: str | None = None, api_key: str = TEST_KEY) -> Any:
    cls = tool_class(name)
    return cls(
        runtime=ToolRuntime(credentials={"api_key": api_key}, user_id="user-1", session_id=None),
        session=SimpleNamespace(app_id=app_id, message_id=message_id),
    )


def run(tool: Any, params: dict[str, Any]) -> dict[str, Any]:
    """Invoke a tool and sort its messages into text, json and variables."""
    out: dict[str, Any] = {"text": [], "json": [], "variables": {}}
    for message in tool.invoke(params):
        kind = message.type.value
        if kind == "text":
            out["text"].append(message.message.text)
        elif kind == "json":
            out["json"].append(message.message.json_object)
        elif kind == "variable":
            out["variables"][message.message.variable_name] = message.message.variable_value
    out["text"] = "\n".join(out["text"])
    out["json"] = out["json"][0] if len(out["json"]) == 1 else out["json"]
    return out
