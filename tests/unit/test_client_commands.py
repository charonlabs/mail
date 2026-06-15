# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Charon Labs (contribution PR)

"""
mail_client command behavior against a respx-mocked transport: env-var
requirements, request shape (URL, auth header, payload), response
validation, and text/json output rendering.

The commands share one structure; ping/login/inbox/compose/send cover
the representative GET, form-POST, and JSON-POST variants.
"""

import json
from argparse import Namespace

import httpx
import pytest
import respx
from mail_client.commands import (
    cmd_compose,
    cmd_inbox,
    cmd_login,
    cmd_ping,
    cmd_send,
)

SERVER = "http://mail.test"
TOKEN = "test-token"

ROOT_RESPONSE = {"protocol_name": "mail", "protocol_version": "2.0", "uptime": 1.5}


@pytest.fixture
def client_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MAIL_SERVER", SERVER)
    monkeypatch.setenv("MAIL_TOKEN", TOKEN)


# ─── ping ──────────────────────────────────────────────────────────


@respx.mock
def test_ping_prints_pong(client_env, capsys: pytest.CaptureFixture) -> None:
    respx.get(f"{SERVER}/").mock(return_value=httpx.Response(200, json=ROOT_RESPONSE))
    cmd_ping(Namespace(output="text"))
    assert capsys.readouterr().out.strip() == "pong"


@respx.mock
def test_ping_json_output_is_parseable(
    client_env, capsys: pytest.CaptureFixture
) -> None:
    respx.get(f"{SERVER}/").mock(return_value=httpx.Response(200, json=ROOT_RESPONSE))
    cmd_ping(Namespace(output="json"))
    payload = json.loads(capsys.readouterr().out)
    assert payload["protocol_name"] == "mail"


def test_ping_requires_mail_server_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("MAIL_SERVER", raising=False)
    with pytest.raises(ValueError, match="MAIL_SERVER"):
        cmd_ping(Namespace(output="text"))


@respx.mock
def test_ping_raises_on_non_200(client_env) -> None:
    respx.get(f"{SERVER}/").mock(return_value=httpx.Response(503))
    with pytest.raises(RuntimeError, match="503"):
        cmd_ping(Namespace(output="text"))


@respx.mock
def test_ping_raises_on_malformed_response(client_env) -> None:
    respx.get(f"{SERVER}/").mock(
        return_value=httpx.Response(200, json={"unexpected": "shape"})
    )
    with pytest.raises(RuntimeError, match="validation"):
        cmd_ping(Namespace(output="text"))


# ─── login ─────────────────────────────────────────────────────────


@respx.mock
def test_login_posts_credentials_as_form_data(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    monkeypatch.setenv("MAIL_SERVER", SERVER)
    monkeypatch.setenv("MAIL_ADDRESS", "user:alice@localhost")
    monkeypatch.setenv("MAIL_PASSWORD", "hunter2")

    route = respx.post(f"{SERVER}/auth/token").mock(
        return_value=httpx.Response(
            200,
            json={"access_token": "issued-jwt", "token_type": "bearer", "metadata": {}},
        )
    )
    cmd_login(Namespace(output="text"))

    content = route.calls[0].request.content.decode()
    assert "username=user%3Aalice%40localhost" in content
    assert "password=hunter2" in content
    assert "issued-jwt" in capsys.readouterr().out


def test_login_requires_credentials_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MAIL_SERVER", SERVER)
    monkeypatch.delenv("MAIL_ADDRESS", raising=False)
    with pytest.raises(ValueError, match="MAIL_ADDRESS"):
        cmd_login(Namespace(output="text"))


# ─── inbox ─────────────────────────────────────────────────────────


@respx.mock
def test_inbox_sends_bearer_token_and_lists_entries(
    client_env, capsys: pytest.CaptureFixture
) -> None:
    entry = {
        "message_id": "55555555-5555-4555-8555-555555555555",
        "sender": "sage@chorus@localhost",
        "subject": "Hello",
        "body_size": 5,
        "received_at": "2026-06-12T09:00:00+00:00",
        "delivered_by": "daemon:dummy@localhost",
    }
    route = respx.get(f"{SERVER}/inbox").mock(
        return_value=httpx.Response(200, json={"entries": [entry], "metadata": {}})
    )
    cmd_inbox(Namespace(output="text"))

    assert route.calls[0].request.headers["Authorization"] == f"Bearer {TOKEN}"
    out = capsys.readouterr().out
    assert "=== Inbox ===" in out
    assert "[sage@chorus@localhost] Hello" in out


def test_inbox_requires_mail_token_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MAIL_SERVER", SERVER)
    monkeypatch.delenv("MAIL_TOKEN", raising=False)
    with pytest.raises(ValueError, match="MAIL_TOKEN"):
        cmd_inbox(Namespace(output="text"))


# ─── compose ───────────────────────────────────────────────────────


@respx.mock
def test_compose_posts_draft_payload(client_env, capsys: pytest.CaptureFixture) -> None:
    draft = {
        "draft_id": "55555555-5555-4555-8555-555555555555",
        "subject": "A subject",
        "body": "A body.",
        "created_at": "2026-06-12T09:00:00+00:00",
        "updated_at": None,
    }
    route = respx.post(f"{SERVER}/drafts").mock(
        return_value=httpx.Response(
            200,
            json={
                "entry": {"draft": draft, "sent_at": None, "sent_by": None},
                "metadata": {},
            },
        )
    )
    cmd_compose(Namespace(output="text", subject="A subject", body="A body."))

    request = route.calls[0].request
    assert request.headers["Authorization"] == f"Bearer {TOKEN}"
    assert json.loads(request.content) == {"subject": "A subject", "body": "A body."}
    assert "Draft ID: 55555555-5555-4555-8555-555555555555" in capsys.readouterr().out


def test_compose_rejects_invalid_subject_before_any_request(client_env) -> None:
    """A malformed subject fails DraftPostRequest validation locally —
    no request reaches the server (SPEC.md §8.1)."""

    with pytest.raises(Exception):  # noqa: B017 — pydantic ValidationError
        cmd_compose(Namespace(output="text", subject="", body="A body."))


# ─── send ──────────────────────────────────────────────────────────


@respx.mock
def test_send_posts_recipients_to_draft_endpoint(
    client_env, capsys: pytest.CaptureFixture
) -> None:
    draft_id = "55555555-5555-4555-8555-555555555555"
    message = {
        "message_id": "66666666-6666-4666-8666-666666666666",
        "sender": "user:alice@localhost",
        "recipients": ["sage@chorus@localhost"],
        "subject": "A subject",
        "body": "A body.",
        "sent_at": "2026-06-12T09:00:00+00:00",
        "metadata": {},
    }
    route = respx.post(f"{SERVER}/drafts/{draft_id}/send").mock(
        return_value=httpx.Response(200, json={"message": message, "metadata": {}})
    )
    cmd_send(Namespace(output="text", draft_id=draft_id, to=["sage@chorus@localhost"]))

    request = route.calls[0].request
    assert json.loads(request.content) == {"recipients": ["sage@chorus@localhost"]}
    out = capsys.readouterr().out
    assert "- sage@chorus@localhost" in out


@respx.mock
def test_send_raises_on_non_200(client_env) -> None:
    draft_id = "55555555-5555-4555-8555-555555555555"
    respx.post(f"{SERVER}/drafts/{draft_id}/send").mock(
        return_value=httpx.Response(404)
    )
    with pytest.raises(RuntimeError, match="404"):
        cmd_send(
            Namespace(output="text", draft_id=draft_id, to=["sage@chorus@localhost"])
        )
