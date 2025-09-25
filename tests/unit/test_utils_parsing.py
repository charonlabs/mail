# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2025 Addison Kline

import json
from typing import Any

import pytest

from mail.utils import parsing


class DummyResponse:
    """
    Simple stub mirroring the interface returned by httpx.get.
    """

    def __init__(self, payload: Any) -> None:
        self._payload = payload

    def json(self) -> Any:
        return self._payload


def test_read_url_string_fetches_json_payload(monkeypatch: pytest.MonkeyPatch) -> None:
    """
    Ensure url-prefixed strings are fetched and converted into JSON strings.
    """

    payload = {"system": "prompt"}

    def fake_get(url: str) -> DummyResponse:
        assert url == "https://example.com/prompt"
        return DummyResponse(payload)

    monkeypatch.setattr(parsing.httpx, "get", fake_get)

    result = parsing.read_url_string("url::https://example.com/prompt")
    assert result == json.dumps(payload)


def test_read_url_string_returns_original_on_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    When fetching fails and raise_on_error is false, return the raw URL.
    """

    def fake_get(_url: str) -> DummyResponse:
        raise RuntimeError("boom")

    monkeypatch.setattr(parsing.httpx, "get", fake_get)

    result = parsing.read_url_string("url::https://example.com/fail")
    assert result == "https://example.com/fail"


def test_read_url_string_raises_with_context(monkeypatch: pytest.MonkeyPatch) -> None:
    """
    If raise_on_error is requested, surface a helpful runtime error.
    """

    def fake_get(_url: str) -> DummyResponse:
        raise RuntimeError("boom")

    monkeypatch.setattr(parsing.httpx, "get", fake_get)

    with pytest.raises(RuntimeError, match="error reading URL string"):
        parsing.read_url_string("url::https://example.com/fail", raise_on_error=True)


def test_resolve_prefixed_string_references_handles_nested_urls(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    Prefixed URL strings inside nested structures are resolved recursively.
    """

    payloads: dict[str, Any] = {
        "https://example.com/system": {"role": "system"},
        "https://example.com/list": ["a", "b"],
    }

    def fake_get(url: str) -> DummyResponse:
        if url not in payloads:
            pytest.fail(f"unexpected URL fetch: {url}")
        return DummyResponse(payloads[url])

    monkeypatch.setattr(parsing.httpx, "get", fake_get)

    data = {
        "system": "url::https://example.com/system",
        "nested": {
            "items": ["plain", "url::https://example.com/list"],
        },
    }

    resolved = parsing.resolve_prefixed_string_references(data)

    assert resolved["system"] == json.dumps(payloads["https://example.com/system"])
    nested_items = resolved["nested"]["items"]
    assert nested_items[0] == "plain"
    assert nested_items[1] == json.dumps(payloads["https://example.com/list"])
