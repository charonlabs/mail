# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Addison Kline

"""
Unit tests for the refresh-token helpers in ``mail_server.auth``: token
generation/hashing, the interactive-principal check, and cookie attributes
(including the ``Secure`` flag, which the integration suite disables so the
TestClient can replay cookies over http).
"""

import hashlib

import mail_server.auth as auth
import pytest
from fastapi import Response
from mail_protocol.core.user_agents import (
    MAILAdmin,
    MAILAgent,
    MAILDaemon,
    MAILUser,
    MAILUserAgent,
    MAILUserAgentInBackend,
)

HOST = "example.com"


def _set_cookie(resp: Response) -> str:
    return resp.headers.get("set-cookie") or ""


def _wrap(ua: MAILUserAgent) -> MAILUserAgentInBackend:
    return MAILUserAgentInBackend(user_agent=ua, hashed_password="x")


def test_generate_refresh_token_prefixed_and_unique() -> None:
    a = auth.generate_refresh_token()
    b = auth.generate_refresh_token()
    assert a.startswith(auth.REFRESH_TOKEN_PREFIX)
    assert b.startswith(auth.REFRESH_TOKEN_PREFIX)
    assert a != b


def test_hash_refresh_token_is_sha256_hex() -> None:
    token = "rt_example"
    assert auth.hash_refresh_token(token) == hashlib.sha256(token.encode()).hexdigest()


def test_is_interactive_principal() -> None:
    assert auth.is_interactive_principal(
        _wrap(MAILUser(ua_type="user", user_id="alice", host=HOST))
    )
    assert auth.is_interactive_principal(
        _wrap(MAILAdmin(ua_type="admin", admin_id="ryan", host=HOST))
    )
    assert not auth.is_interactive_principal(
        _wrap(MAILAgent(ua_type="agent", name="sage", swarm="chorus", host=HOST))
    )
    assert not auth.is_interactive_principal(
        _wrap(MAILDaemon(ua_type="daemon", worker_name="dummy", host=HOST))
    )


def test_set_refresh_cookie_secure_when_configured(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(auth, "COOKIE_SECURE", True)
    resp = Response()
    auth.set_refresh_cookie(resp, "rt_value")

    header = _set_cookie(resp)
    lowered = header.lower()
    assert f"{auth.REFRESH_COOKIE_NAME}=rt_value" in header
    assert "secure" in lowered
    assert "httponly" in lowered
    assert "samesite=strict" in lowered
    assert "path=/auth" in lowered


def test_set_refresh_cookie_omits_secure_when_disabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(auth, "COOKIE_SECURE", False)
    resp = Response()
    auth.set_refresh_cookie(resp, "rt_value")

    assert "secure" not in _set_cookie(resp).lower()


def test_clear_refresh_cookie_emits_deletion() -> None:
    resp = Response()
    auth.clear_refresh_cookie(resp)

    lowered = _set_cookie(resp).lower()
    assert f"{auth.REFRESH_COOKIE_NAME}=" in lowered
    assert "path=/auth" in lowered
    # deletion is expressed as an immediate expiry
    assert "max-age=0" in lowered or 'expires=thu, 01 jan 1970' in lowered
