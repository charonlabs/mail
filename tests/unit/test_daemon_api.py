# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Charon Labs (contribution PR)

"""
mail_daemon.maild.api behavior against a respx-mocked transport:
startup validation, token acquisition, buffer clearing, delivery, and
the poll loop. The module keeps its connection state in module-level
globals; the `daemon_state` fixture sets them via monkeypatch so each
test starts clean and the originals are restored afterward.
"""

from argparse import Namespace

import httpx
import pytest
import respx
from mail_daemon.maild import api as maild

SERVER = "http://mail.test"
TOKEN = "daemon-jwt"

ROOT_RESPONSE = {"protocol_name": "mail", "protocol_version": "2.0", "uptime": 1.5}
TOKEN_RESPONSE = {"access_token": TOKEN, "token_type": "bearer", "metadata": {}}


def _whoami_response(ua_type: str = "daemon") -> dict:
    match ua_type:
        case "daemon":
            user_agent = {
                "ua_type": "daemon",
                "worker_name": "dummy",
                "host": "localhost",
            }
        case "user":
            user_agent = {"ua_type": "user", "user_id": "alice", "host": "localhost"}
        case _:
            raise ValueError(ua_type)
    return {"user_agent": {"user_agent": user_agent}, "metadata": {}}


@pytest.fixture
def daemon_state(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(maild, "_mail_server", SERVER)
    monkeypatch.setattr(maild, "_mail_address", "daemon:dummy@localhost")
    monkeypatch.setattr(maild, "_mail_password", "pw")
    monkeypatch.setattr(maild, "_mail_token", TOKEN)


# ─── startup validation ────────────────────────────────────────────


def test_check_env_vars_populates_globals(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MAIL_SERVER", SERVER)
    monkeypatch.setenv("MAIL_ADDRESS", "daemon:dummy@localhost")
    monkeypatch.setenv("MAIL_PASSWORD", "pw")
    monkeypatch.setattr(maild, "_mail_server", None)
    monkeypatch.setattr(maild, "_mail_address", None)
    monkeypatch.setattr(maild, "_mail_password", None)

    maild._check_env_vars()
    assert maild._mail_server == SERVER
    assert maild._mail_address == "daemon:dummy@localhost"
    assert maild._mail_password == "pw"


@pytest.mark.parametrize("missing", ["MAIL_SERVER", "MAIL_ADDRESS", "MAIL_PASSWORD"])
def test_check_env_vars_requires_each_var(
    monkeypatch: pytest.MonkeyPatch, missing: str
) -> None:
    for var in ("MAIL_SERVER", "MAIL_ADDRESS", "MAIL_PASSWORD"):
        monkeypatch.setenv(var, "set")
    monkeypatch.delenv(missing)
    with pytest.raises(ValueError, match=missing):
        maild._check_env_vars()


@respx.mock
def test_check_server_accepts_valid_mail_server(daemon_state) -> None:
    respx.get(SERVER).mock(return_value=httpx.Response(200, json=ROOT_RESPONSE))
    maild._check_server()  # no exception


@respx.mock
def test_check_server_rejects_non_200(daemon_state) -> None:
    respx.get(SERVER).mock(return_value=httpx.Response(503))
    with pytest.raises(RuntimeError, match="503"):
        maild._check_server()


@respx.mock
def test_check_server_rejects_non_mail_server(daemon_state) -> None:
    respx.get(SERVER).mock(return_value=httpx.Response(200, json={"hello": "world"}))
    with pytest.raises(ValueError, match="GET /"):
        maild._check_server()


# ─── token acquisition ─────────────────────────────────────────────


@respx.mock
def test_obtain_daemon_token_logs_in_and_verifies_role(daemon_state) -> None:
    respx.post(f"{SERVER}/auth/token").mock(
        return_value=httpx.Response(200, json=TOKEN_RESPONSE)
    )
    whoami = respx.get(f"{SERVER}/auth/whoami").mock(
        return_value=httpx.Response(200, json=_whoami_response("daemon"))
    )

    maild._obtain_daemon_token()
    assert maild._mail_token == TOKEN
    assert whoami.calls[0].request.headers["Authorization"] == f"Bearer {TOKEN}"


@respx.mock
def test_obtain_daemon_token_rejects_non_daemon_credentials(daemon_state) -> None:
    respx.post(f"{SERVER}/auth/token").mock(
        return_value=httpx.Response(200, json=TOKEN_RESPONSE)
    )
    respx.get(f"{SERVER}/auth/whoami").mock(
        return_value=httpx.Response(200, json=_whoami_response("user"))
    )
    with pytest.raises(ValueError, match="user"):
        maild._obtain_daemon_token()


@respx.mock
def test_obtain_daemon_token_raises_on_login_failure(daemon_state) -> None:
    respx.post(f"{SERVER}/auth/token").mock(return_value=httpx.Response(401))
    with pytest.raises(RuntimeError, match="401"):
        maild._obtain_daemon_token()


# ─── clear_message_buffer ──────────────────────────────────────────


@respx.mock
def test_clear_message_buffer_returns_ids(daemon_state) -> None:
    route = respx.post(f"{SERVER}/daemon/message-buffer/clear").mock(
        return_value=httpx.Response(
            200,
            json={
                "message_ids": ["55555555-5555-4555-8555-555555555555"],
                "metadata": {},
            },
        )
    )
    assert maild.clear_message_buffer() == ["55555555-5555-4555-8555-555555555555"]
    assert route.calls[0].request.headers["Authorization"] == f"Bearer {TOKEN}"


@respx.mock
@pytest.mark.parametrize(
    "response",
    [
        httpx.Response(503),
        httpx.Response(200, json={"unexpected": "shape"}),
    ],
)
def test_clear_message_buffer_returns_empty_on_bad_response(
    daemon_state, response: httpx.Response
) -> None:
    respx.post(f"{SERVER}/daemon/message-buffer/clear").mock(return_value=response)
    assert maild.clear_message_buffer() == []


@respx.mock
def test_clear_message_buffer_returns_empty_on_network_error(daemon_state) -> None:
    respx.post(f"{SERVER}/daemon/message-buffer/clear").mock(
        side_effect=httpx.ConnectError("connection refused")
    )
    assert maild.clear_message_buffer() == []


# ─── deliver_messages ──────────────────────────────────────────────


@respx.mock
def test_deliver_messages_posts_ids(daemon_state) -> None:
    message_id = "55555555-5555-4555-8555-555555555555"
    summary = {
        "message_id": message_id,
        "sender": "user:alice@localhost",
        "recipients": ["sage@chorus@localhost"],
        "subject": "Hello",
        "body_size": 5,
        "sent_at": "2026-06-12T09:00:00+00:00",
    }
    route = respx.post(f"{SERVER}/daemon/deliver/local").mock(
        return_value=httpx.Response(200, json={"messages": [summary], "metadata": {}})
    )
    maild.deliver_messages([message_id])

    import json

    assert json.loads(route.calls[0].request.content) == {"message_ids": [message_id]}


@respx.mock
def test_deliver_messages_reauthenticates_on_401(
    daemon_state, monkeypatch: pytest.MonkeyPatch
) -> None:
    respx.post(f"{SERVER}/daemon/deliver/local").mock(
        return_value=httpx.Response(401)
    )
    relogins: list[bool] = []
    monkeypatch.setattr(maild, "_obtain_daemon_token", lambda: relogins.append(True))

    maild.deliver_messages(["55555555-5555-4555-8555-555555555555"])
    assert relogins == [True]


@respx.mock
def test_deliver_messages_warns_on_count_mismatch(
    daemon_state, caplog: pytest.LogCaptureFixture
) -> None:
    respx.post(f"{SERVER}/daemon/deliver/local").mock(
        return_value=httpx.Response(200, json={"messages": [], "metadata": {}})
    )
    with caplog.at_level("WARNING", logger="maild"):
        maild.deliver_messages(["55555555-5555-4555-8555-555555555555"])
    assert "mismatch" in caplog.text


# ─── daemon_loop ───────────────────────────────────────────────────


def test_daemon_loop_clears_then_delivers_each_iteration(
    daemon_state, monkeypatch: pytest.MonkeyPatch
) -> None:
    delivered: list[list[str]] = []
    monkeypatch.setattr(
        maild, "clear_message_buffer", lambda: ["55555555-5555-4555-8555-555555555555"]
    )
    monkeypatch.setattr(maild, "deliver_messages", delivered.append)

    def interrupt(_seconds: int) -> None:
        raise KeyboardInterrupt

    monkeypatch.setattr(maild, "sleep", interrupt)

    maild.daemon_loop()  # exits cleanly on KeyboardInterrupt
    assert delivered == [["55555555-5555-4555-8555-555555555555"]]


# ─── run_daemon wiring ─────────────────────────────────────────────


def test_run_daemon_validates_before_looping(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []
    monkeypatch.setattr(maild, "_check_env_vars", lambda: calls.append("env"))
    monkeypatch.setattr(maild, "_check_server", lambda: calls.append("server"))
    monkeypatch.setattr(maild, "_obtain_daemon_token", lambda: calls.append("token"))
    monkeypatch.setattr(maild, "daemon_loop", lambda: calls.append("loop"))

    maild.run_daemon(Namespace())
    assert calls == ["env", "server", "token", "loop"]
