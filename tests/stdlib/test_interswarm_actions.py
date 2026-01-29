# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2025 Addison Kline

import aiohttp
import pytest

from mail.stdlib.interswarm import (
    get_swarm_health,
    get_swarm_registry,
    ping_swarm,
)


class _DummyResponse:
    def __init__(self, *, status: int, json_data: dict, text_data: str = ""):
        self.status = status
        self._json = json_data
        self._text = text_data

    async def json(self):
        return self._json

    async def text(self):
        return self._text


class _DummyContext:
    def __init__(self, response: _DummyResponse):
        self._response = response

    async def __aenter__(self):
        return self._response

    async def __aexit__(self, *_args):
        return False


def _patch_session(
    monkeypatch: pytest.MonkeyPatch, routes: dict[str, _DummyResponse]
) -> None:
    class _DummySession:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return False

        def get(self, url: str, **_kwargs):
            key = f"GET:{url}"
            return _DummyContext(routes[key])

    monkeypatch.setattr(aiohttp, "ClientSession", _DummySession)


@pytest.mark.asyncio
async def test_ping_swarm_returns_pong(monkeypatch: pytest.MonkeyPatch) -> None:
    """
    Test that the `ping_swarm` action returns "pong" if the remote swarm is valid.
    """
    url = "https://remote.swarm"
    routes = {
        f"GET:{url}": _DummyResponse(
            status=200,
            json_data={
                "name": "mail",
                "swarm": {"name": "remote", "entrypoint": "supervisor"},
                "status": "running",
            },
        )
    }
    _patch_session(monkeypatch, routes)

    result = await ping_swarm.function({"url": url})  # type: ignore[arg-type]
    assert result == "pong"


@pytest.mark.asyncio
async def test_get_swarm_health_returns_status(monkeypatch: pytest.MonkeyPatch) -> None:
    """
    Test that the `get_swarm_health` action returns the status of the remote swarm.
    """
    url = "https://remote.swarm"
    routes = {
        f"GET:{url}/health": _DummyResponse(
            status=200,
            json_data={"status": "ok", "swarm_name": "remote"},
        )
    }
    _patch_session(monkeypatch, routes)

    result = await get_swarm_health.function({"url": url})  # type: ignore[arg-type]
    assert result == "ok"


@pytest.mark.asyncio
async def test_get_swarm_registry_returns_joined_rows(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    Test that the `get_swarm_registry` action returns a newline-delimited list of the remote swarm's registered swarms.
    """
    url = "https://remote.swarm"
    routes = {
        f"GET:{url}/swarms": _DummyResponse(
            status=200,
            json_data={
                "swarms": [
                    {"swarm_name": "alpha", "base_url": "https://alpha"},
                    {"swarm_name": "beta", "base_url": "https://beta"},
                ]
            },
        )
    }
    _patch_session(monkeypatch, routes)

    result = await get_swarm_registry.function({"url": url})  # type: ignore[arg-type]
    assert result == "alpha@https://alpha\nbeta@https://beta"


@pytest.mark.asyncio
async def test_ping_swarm_missing_url_returns_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    Test that the `ping_swarm` action returns an error if the URL is missing.
    """
    _patch_session(monkeypatch, {})

    result = await ping_swarm.function({})  # type: ignore[arg-type]
    assert result.startswith("Error")
