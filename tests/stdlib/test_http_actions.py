# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2025 Addison Kline

from typing import Any

import aiohttp
import pytest

from mail.stdlib.http import (
    http_delete,
    http_get,
    http_head,
    http_options,
    http_patch,
    http_post,
    http_put,
)


class _DummyResponse:
    def __init__(self, text: str):
        self._text = text

    async def text(self) -> str:
        return self._text


class _DummyContext:
    def __init__(self, response: _DummyResponse):
        self._response = response

    async def __aenter__(self):
        return self._response

    async def __aexit__(self, *_args):
        return False


def _make_session(
    monkeypatch: pytest.MonkeyPatch,
    responses: dict[str, str],
    calls: list[tuple[str, str, dict[str, Any]]],
) -> None:
    class _DummySession:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return False

        def _ctx(self, method: str, url: str, kwargs: dict[str, Any]):
            calls.append((method, url, kwargs))
            key = f"{method}:{url}"
            text = responses.get(key, "")
            return _DummyContext(_DummyResponse(text))

        def get(self, url: str, **kwargs):
            return self._ctx("GET", url, kwargs)

        def post(self, url: str, **kwargs):
            return self._ctx("POST", url, kwargs)

        def put(self, url: str, **kwargs):
            return self._ctx("PUT", url, kwargs)

        def delete(self, url: str, **kwargs):
            return self._ctx("DELETE", url, kwargs)

        def patch(self, url: str, **kwargs):
            return self._ctx("PATCH", url, kwargs)

        def head(self, url: str, **kwargs):
            return self._ctx("HEAD", url, kwargs)

        def options(self, url: str, **kwargs):
            return self._ctx("OPTIONS", url, kwargs)

    monkeypatch.setattr(aiohttp, "ClientSession", _DummySession)


@pytest.mark.asyncio
async def test_http_get_returns_body(monkeypatch: pytest.MonkeyPatch) -> None:
    """
    Test that the `http_get` action returns the body of the response.
    """
    calls: list[tuple[str, str, dict[str, Any]]] = []
    responses = {"GET:https://api.example.com": "ok"}
    _make_session(monkeypatch, responses, calls)

    payload = {"url": "https://api.example.com"}
    result = await http_get.function(payload)  # type: ignore[arg-type]

    assert result == "ok"
    assert calls == [("GET", "https://api.example.com", {})]


@pytest.mark.asyncio
async def test_http_post_sends_json(monkeypatch: pytest.MonkeyPatch) -> None:
    """
    Test that the `http_post` action sends a JSON payload.
    """
    calls: list[tuple[str, str, dict[str, Any]]] = []
    responses = {"POST:https://api.example.com": "posted"}
    _make_session(monkeypatch, responses, calls)

    payload = {
        "url": "https://api.example.com",
        "headers": {"Content-Type": "application/json"},
        "body": {"message": "hi"},
    }
    result = await http_post.function(payload)  # type: ignore[arg-type]

    assert result == "posted"
    method, url, kwargs = calls[0]
    assert method == "POST"
    assert url == "https://api.example.com"
    assert kwargs["headers"] == {"Content-Type": "application/json"}
    assert kwargs["json"] == {"message": "hi"}


@pytest.mark.asyncio
async def test_http_patch_and_delete(monkeypatch: pytest.MonkeyPatch) -> None:
    """
    Test that the `http_patch` and `http_delete` actions work.
    """
    calls: list[tuple[str, str, dict[str, Any]]] = []
    responses = {
        "PATCH:https://api.example.com/resource": "patched",
        "DELETE:https://api.example.com/resource": "deleted",
    }
    _make_session(monkeypatch, responses, calls)

    patch_payload = {
        "url": "https://api.example.com/resource",
        "body": {"field": "value"},
    }
    delete_payload = {"url": "https://api.example.com/resource"}

    patch_result = await http_patch.function(patch_payload)  # type: ignore[arg-type]
    delete_result = await http_delete.function(delete_payload)  # type: ignore[arg-type]

    assert patch_result == "patched"
    assert delete_result == "deleted"

    assert (
        "PATCH",
        "https://api.example.com/resource",
        {"headers": None, "json": {"field": "value"}},
    ) in calls
    assert ("DELETE", "https://api.example.com/resource", {}) in calls


@pytest.mark.asyncio
async def test_http_head_and_options_forward_headers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    Test that the `http_head` and `http_options` actions forward headers.
    """
    calls: list[tuple[str, str, dict[str, Any]]] = []
    responses = {
        "HEAD:https://api.example.com": "",
        "OPTIONS:https://api.example.com": "options",
    }
    _make_session(monkeypatch, responses, calls)

    headers = {"Authorization": "Bearer token"}
    await http_head.function({"url": "https://api.example.com", "headers": headers})  # type: ignore[arg-type]
    await http_options.function({"url": "https://api.example.com", "headers": headers})  # type: ignore[arg-type]

    assert calls[0][0] == "HEAD"
    assert calls[0][2]["headers"] == headers
    assert calls[1][0] == "OPTIONS"
    assert calls[1][2]["headers"] == headers


@pytest.mark.asyncio
async def test_http_post_missing_headers_returns_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    Test that the `http_post` action returns an error if the headers are missing.
    """
    calls: list[tuple[str, str, dict[str, Any]]] = []
    responses: dict[str, str] = {}
    _make_session(monkeypatch, responses, calls)

    payload = {"url": "https://api.example.com", "body": {}}
    result = await http_post.function(payload)  # type: ignore[arg-type]
    assert result.startswith("Error")
