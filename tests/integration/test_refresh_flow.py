# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Addison Kline

"""
HTTP-level tests for the refresh-token flow (``POST /auth/token`` issuance,
``POST /auth/refresh`` rotation + reuse detection, ``POST /auth/logout``, and
the password-reset cascade). Every test runs against both backends via the
parametrized ``app_client`` fixture.

The ``Secure`` cookie flag is disabled for the suite (see ``tests/conftest.py``)
so the TestClient replays the cookie over http; ``test_login_cookie_attributes``
asserts the remaining hardening attributes.
"""

from collections.abc import Callable
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

ADMIN = "admin:ryan@localhost"
USER = "user:alice@localhost"
AGENT = "sage@chorus@localhost"
DAEMON = "daemon:dummy@localhost"
PASSWORD = "correct-horse-battery-staple"


def _login(client: TestClient, address: str, password: str = PASSWORD):
    return client.post(
        "/auth/token", data={"username": address, "password": password}
    )


def _refresh_body(client: TestClient, token: str):
    """Refresh via the body path — cookies cleared so the cookie can't win."""

    client.cookies.clear()
    return client.post("/auth/refresh", json={"refresh_token": token})


# ─── issuance ──────────────────────────────────────────────────────


@pytest.mark.parametrize("address", [USER, ADMIN])
def test_login_issues_refresh_token_for_interactive(
    app_client: TestClient, address: str
) -> None:
    app_client.cookies.clear()
    resp = _login(app_client, address)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["refresh_token"] is not None
    assert body["refresh_token"].startswith("rt_")
    assert body["expires_in"] > 0
    assert "mail_refresh_token=" in (resp.headers.get("set-cookie") or "")


@pytest.mark.parametrize("address", [AGENT, DAEMON])
def test_login_no_refresh_token_for_non_interactive(
    app_client: TestClient, address: str
) -> None:
    app_client.cookies.clear()
    resp = _login(app_client, address)
    assert resp.status_code == 200, resp.text
    assert resp.json()["refresh_token"] is None
    assert resp.headers.get("set-cookie") is None


def test_login_cookie_attributes(app_client: TestClient) -> None:
    app_client.cookies.clear()
    resp = _login(app_client, USER)
    set_cookie = (resp.headers.get("set-cookie") or "").lower()
    assert "httponly" in set_cookie
    assert "samesite=strict" in set_cookie
    assert "path=/auth" in set_cookie


# ─── refresh / rotation ────────────────────────────────────────────


def test_refresh_via_cookie_rotates(app_client: TestClient) -> None:
    app_client.cookies.clear()
    old = _login(app_client, USER).json()["refresh_token"]

    # cookie from login is replayed automatically
    resp = app_client.post("/auth/refresh")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["access_token"]
    assert body["refresh_token"] and body["refresh_token"] != old

    # the consumed token is now dead (reuse → 401)
    assert _refresh_body(app_client, old).status_code == 401


def test_refresh_via_body(app_client: TestClient) -> None:
    app_client.cookies.clear()
    token = _login(app_client, USER).json()["refresh_token"]

    resp = _refresh_body(app_client, token)
    assert resp.status_code == 200, resp.text
    assert resp.json()["refresh_token"] != token


def test_reuse_revokes_whole_family(app_client: TestClient) -> None:
    app_client.cookies.clear()
    t0 = _login(app_client, USER).json()["refresh_token"]

    t1 = _refresh_body(app_client, t0).json()["refresh_token"]

    # replaying the already-rotated t0 is reuse → 401 and nukes the family
    assert _refresh_body(app_client, t0).status_code == 401
    # the live sibling t1 is now collateral-revoked
    assert _refresh_body(app_client, t1).status_code == 401


def test_refresh_unknown_token_401(app_client: TestClient) -> None:
    assert _refresh_body(app_client, "rt_does-not-exist").status_code == 401


def test_refresh_without_token_401(app_client: TestClient) -> None:
    app_client.cookies.clear()
    assert app_client.post("/auth/refresh").status_code == 401


def test_refresh_expired_token_401(
    app_client: TestClient, seed_refresh_token: Callable[..., str]
) -> None:
    token = seed_refresh_token(
        USER, "rt_expired", expires_at=datetime.now(UTC) - timedelta(seconds=1)
    )
    assert _refresh_body(app_client, token).status_code == 401


def test_refresh_after_owner_deleted_401(
    app_client: TestClient, headers_for: Callable[..., dict[str, str]]
) -> None:
    app_client.cookies.clear()
    token = _login(app_client, USER).json()["refresh_token"]

    deleted = app_client.delete("/admin/users/alice", headers=headers_for(ADMIN))
    assert deleted.status_code == 200, deleted.text

    assert _refresh_body(app_client, token).status_code == 401


# ─── logout ────────────────────────────────────────────────────────


def test_logout_revokes_family_and_succeeds(app_client: TestClient) -> None:
    app_client.cookies.clear()
    token = _login(app_client, USER).json()["refresh_token"]

    out = app_client.post("/auth/logout")
    assert out.status_code == 200, out.text
    assert out.json()["status"] == "success"

    assert _refresh_body(app_client, token).status_code == 401


def test_logout_without_token_is_idempotent(app_client: TestClient) -> None:
    app_client.cookies.clear()
    out = app_client.post("/auth/logout")
    assert out.status_code == 200
    assert out.json()["status"] == "success"


# ─── password reset cascade ────────────────────────────────────────


def test_password_reset_revokes_refresh_tokens(
    app_client: TestClient, headers_for: Callable[..., dict[str, str]]
) -> None:
    app_client.cookies.clear()
    token = _login(app_client, USER).json()["refresh_token"]

    reset = app_client.post(
        "/auth/password/reset",
        json={"current_password": PASSWORD, "new_password": "new-passw0rd-here"},
        headers=headers_for(USER),
    )
    assert reset.status_code == 200, reset.text

    assert _refresh_body(app_client, token).status_code == 401
