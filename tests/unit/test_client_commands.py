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
    cmd_drafts_patch,
    cmd_forward,
    cmd_inbox,
    cmd_login,
    cmd_ping,
    cmd_refresh,
    cmd_reply,
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
            json={
                "access_token": "issued-jwt",
                "token_type": "bearer",
                "expires_in": 900,
                "metadata": {},
            },
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


# ─── refresh ───────────────────────────────────────────────────────


@respx.mock
def test_refresh_posts_token_in_body_and_prints_rotated(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    monkeypatch.setenv("MAIL_SERVER", SERVER)
    monkeypatch.setenv("MAIL_REFRESH_TOKEN", "rt_old")

    route = respx.post(f"{SERVER}/auth/refresh").mock(
        return_value=httpx.Response(
            200,
            json={
                "access_token": "fresh-jwt",
                "token_type": "bearer",
                "refresh_token": "rt_new",
                "expires_in": 900,
                "metadata": {},
            },
        )
    )
    cmd_refresh(Namespace(output="text"))

    sent = json.loads(route.calls[0].request.content.decode())
    assert sent == {"refresh_token": "rt_old"}
    out = capsys.readouterr().out
    assert "fresh-jwt" in out
    assert "rt_new" in out


def test_refresh_requires_refresh_token_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MAIL_SERVER", SERVER)
    monkeypatch.delenv("MAIL_REFRESH_TOKEN", raising=False)
    with pytest.raises(ValueError, match="MAIL_REFRESH_TOKEN"):
        cmd_refresh(Namespace(output="text"))


@respx.mock
def test_refresh_raises_on_401(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MAIL_SERVER", SERVER)
    monkeypatch.setenv("MAIL_REFRESH_TOKEN", "rt_dead")
    respx.post(f"{SERVER}/auth/refresh").mock(return_value=httpx.Response(401))
    with pytest.raises(RuntimeError, match="401"):
        cmd_refresh(Namespace(output="text"))


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
    cmd_compose(
        Namespace(
            output="text", subject="A subject", body="A body.", body_file=None, tags=[]
        )
    )

    request = route.calls[0].request
    assert request.headers["Authorization"] == f"Bearer {TOKEN}"
    assert json.loads(request.content) == {
        "subject": "A subject",
        "body": "A body.",
        "reply_to": None,
        "tags": [],
    }
    assert "Draft ID: 55555555-5555-4555-8555-555555555555" in capsys.readouterr().out


@respx.mock
def test_compose_reads_body_from_file(
    client_env, tmp_path, capsys: pytest.CaptureFixture
) -> None:
    body_path = tmp_path / "message.md"
    body_path.write_text("Body from a file.", encoding="utf-8")
    route = respx.post(f"{SERVER}/drafts").mock(
        return_value=httpx.Response(
            200,
            json={
                "entry": {
                    "draft": {
                        "draft_id": "55555555-5555-4555-8555-555555555555",
                        "subject": "A subject",
                        "body": "Body from a file.",
                        "created_at": "2026-06-12T09:00:00+00:00",
                        "updated_at": None,
                    },
                    "sent_at": None,
                    "sent_by": None,
                },
                "metadata": {},
            },
        )
    )
    cmd_compose(
        Namespace(
            output="text",
            subject="A subject",
            body=None,
            body_file=str(body_path),
            tags=[],
        )
    )

    assert json.loads(route.calls[0].request.content)["body"] == "Body from a file."


def test_compose_rejects_both_body_and_body_file(client_env, tmp_path) -> None:
    body_path = tmp_path / "message.md"
    body_path.write_text("From file.", encoding="utf-8")
    with pytest.raises(Exception):  # noqa: B017 — ValueError from resolve_body
        cmd_compose(
            Namespace(
                output="text",
                subject="A subject",
                body="Inline.",
                body_file=str(body_path),
                tags=[],
            )
        )


def test_compose_rejects_missing_body(client_env) -> None:
    with pytest.raises(Exception):  # noqa: B017 — ValueError from resolve_body
        cmd_compose(
            Namespace(
                output="text", subject="A subject", body=None, body_file=None, tags=[]
            )
        )


def test_compose_rejects_invalid_subject_before_any_request(client_env) -> None:
    """A malformed subject fails DraftPostRequest validation locally —
    no request reaches the server (SPEC.md §8.1)."""

    with pytest.raises(Exception):  # noqa: B017 — pydantic ValidationError
        cmd_compose(
            Namespace(
                output="text", subject="", body="A body.", body_file=None, tags=[]
            )
        )


# ─── draft-edit ────────────────────────────────────────────────────


@respx.mock
def test_draft_edit_patches_supplied_fields(
    client_env, capsys: pytest.CaptureFixture
) -> None:
    draft_id = "55555555-5555-4555-8555-555555555555"
    route = respx.patch(f"{SERVER}/drafts/{draft_id}").mock(
        return_value=httpx.Response(
            200,
            json={
                "entry": {
                    "draft": {
                        "draft_id": draft_id,
                        "subject": "New subject",
                        "body": "Old body.",
                        "created_at": "2026-06-12T09:00:00+00:00",
                        "updated_at": "2026-06-12T10:00:00+00:00",
                        "tags": ["x"],
                    },
                    "sent_at": None,
                    "sent_by": None,
                },
                "metadata": {},
            },
        )
    )
    cmd_drafts_patch(
        Namespace(
            output="text",
            draft_id=draft_id,
            subject="New subject",
            body=None,
            body_file=None,
            reply_to=None,
            tags=None,
        )
    )

    request = route.calls[0].request
    assert request.method == "PATCH"
    assert json.loads(request.content) == {
        "subject": "New subject",
        "body": None,
        "reply_to": None,
        "tags": None,
    }
    assert "Subject: New subject" in capsys.readouterr().out


# ─── send ──────────────────────────────────────────────────────────


@respx.mock
def test_send_posts_recipients_to_draft_endpoint(
    client_env, capsys: pytest.CaptureFixture
) -> None:
    draft_id = "55555555-5555-4555-8555-555555555555"
    message = {
        "mail_version": "2.0",
        "message_id": "66666666-6666-4666-8666-666666666666",
        "sender": "user:alice@localhost",
        "recipients": ["sage@chorus@localhost"],
        "subject": "A subject",
        "body": "A body.",
        "tags": [],
        "sent_at": "2026-06-12T09:00:00+00:00",
        "metadata": {},
    }
    route = respx.post(f"{SERVER}/drafts/{draft_id}/send").mock(
        return_value=httpx.Response(200, json={"message": message, "metadata": {}})
    )
    cmd_send(
        Namespace(
            output="text", draft_id=draft_id, to=["sage@chorus@localhost"], tags=[]
        )
    )

    request = route.calls[0].request
    assert json.loads(request.content) == {
        "recipients": ["sage@chorus@localhost"],
        "tags": [],
    }
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
            Namespace(
                output="text",
                draft_id=draft_id,
                to=["sage@chorus@localhost"],
                tags=[],
            )
        )


# ─── reply ─────────────────────────────────────────────────────────


def _inbox_entry(message: dict) -> dict:
    return {
        "entry": {
            "message": message,
            "received_at": "2026-06-12T09:05:00+00:00",
            "delivered_by": "daemon:worker@localhost",
        },
        "metadata": {},
    }


ORIGINAL_ID = "66666666-6666-4666-8666-666666666666"
ORIGINAL_MESSAGE = {
    "mail_version": "2.0",
    "message_id": ORIGINAL_ID,
    "sender": "philosopher@chorus@localhost",
    "recipients": ["user:alice@localhost"],
    "subject": "Original subject",
    "body": "The original body.",
    "tags": [],
    "sent_at": "2026-06-12T09:00:00+00:00",
    "metadata": {},
}


def _mock_reply_routes(draft_id: str, reply_message: dict):
    """Register the three calls a reply makes: fetch, draft, send."""

    inbox_route = respx.get(f"{SERVER}/inbox/{ORIGINAL_ID}").mock(
        return_value=httpx.Response(200, json=_inbox_entry(ORIGINAL_MESSAGE))
    )
    draft = {
        "draft_id": draft_id,
        "subject": reply_message["subject"],
        "body": reply_message["body"],
        "created_at": "2026-06-12T09:10:00+00:00",
        "updated_at": None,
        "reply_to": ORIGINAL_ID,
        "tags": reply_message["tags"],
    }
    draft_route = respx.post(f"{SERVER}/drafts").mock(
        return_value=httpx.Response(
            200,
            json={
                "entry": {"draft": draft, "sent_at": None, "sent_by": None},
                "metadata": {},
            },
        )
    )
    send_route = respx.post(f"{SERVER}/drafts/{draft_id}/send").mock(
        return_value=httpx.Response(
            200, json={"message": reply_message, "metadata": {}}
        )
    )
    return inbox_route, draft_route, send_route


@respx.mock
def test_reply_defaults_subject_recipient_and_reply_to(
    client_env, capsys: pytest.CaptureFixture
) -> None:
    draft_id = "55555555-5555-4555-8555-555555555555"
    reply_message = {
        "mail_version": "2.0",
        "message_id": "77777777-7777-4777-8777-777777777777",
        "reply_to": ORIGINAL_ID,
        "sender": "user:alice@localhost",
        "recipients": ["philosopher@chorus@localhost"],
        "subject": "Re: Original subject",
        "body": "My reply.",
        "tags": [],
        "sent_at": "2026-06-12T09:11:00+00:00",
        "metadata": {},
    }
    _, draft_route, send_route = _mock_reply_routes(draft_id, reply_message)

    cmd_reply(
        Namespace(
            output="text",
            message_id=ORIGINAL_ID,
            body="My reply.",
            subject=None,
            tags=[],
        )
    )

    # The draft references the original and defaults the subject to "Re: ...".
    draft_body = json.loads(draft_route.calls[0].request.content)
    assert draft_body == {
        "subject": "Re: Original subject",
        "body": "My reply.",
        "reply_to": ORIGINAL_ID,
        "tags": [],
    }
    # The reply is addressed back to the original sender.
    send_body = json.loads(send_route.calls[0].request.content)
    assert send_body == {
        "recipients": ["philosopher@chorus@localhost"],
        "tags": [],
    }
    out = capsys.readouterr().out
    assert "Reply Sent" in out
    assert f"In Reply To: {ORIGINAL_ID}" in out


@respx.mock
def test_reply_honors_explicit_subject_and_tags(
    client_env, capsys: pytest.CaptureFixture
) -> None:
    draft_id = "55555555-5555-4555-8555-555555555555"
    reply_message = {
        "mail_version": "2.0",
        "message_id": "77777777-7777-4777-8777-777777777777",
        "reply_to": ORIGINAL_ID,
        "sender": "user:alice@localhost",
        "recipients": ["philosopher@chorus@localhost"],
        "subject": "Custom subject",
        "body": "My reply.",
        "tags": ["urgent", "project-x"],
        "sent_at": "2026-06-12T09:11:00+00:00",
        "metadata": {},
    }
    _, draft_route, _ = _mock_reply_routes(draft_id, reply_message)

    cmd_reply(
        Namespace(
            output="text",
            message_id=ORIGINAL_ID,
            body="My reply.",
            subject="Custom subject",
            tags=["urgent", "project-x"],
        )
    )

    draft_body = json.loads(draft_route.calls[0].request.content)
    assert draft_body["subject"] == "Custom subject"
    assert draft_body["tags"] == ["urgent", "project-x"]


@respx.mock
def test_reply_raises_when_original_missing(client_env) -> None:
    respx.get(f"{SERVER}/inbox/{ORIGINAL_ID}").mock(return_value=httpx.Response(404))
    with pytest.raises(RuntimeError, match="404"):
        cmd_reply(
            Namespace(
                output="text",
                message_id=ORIGINAL_ID,
                body="My reply.",
                subject=None,
                tags=[],
            )
        )


# ─── forward ───────────────────────────────────────────────────────


def _mock_forward_routes(draft_id: str, forwarded_message: dict):
    """Register the three calls a forward makes: fetch, draft, send."""

    inbox_route = respx.get(f"{SERVER}/inbox/{ORIGINAL_ID}").mock(
        return_value=httpx.Response(200, json=_inbox_entry(ORIGINAL_MESSAGE))
    )
    draft = {
        "draft_id": draft_id,
        "subject": forwarded_message["subject"],
        "body": forwarded_message["body"],
        "created_at": "2026-06-12T09:10:00+00:00",
        "updated_at": None,
        "reply_to": None,
        "tags": forwarded_message["tags"],
    }
    draft_route = respx.post(f"{SERVER}/drafts").mock(
        return_value=httpx.Response(
            200,
            json={
                "entry": {"draft": draft, "sent_at": None, "sent_by": None},
                "metadata": {},
            },
        )
    )
    send_route = respx.post(f"{SERVER}/drafts/{draft_id}/send").mock(
        return_value=httpx.Response(
            200, json={"message": forwarded_message, "metadata": {}}
        )
    )
    return inbox_route, draft_route, send_route


@respx.mock
def test_forward_defaults_subject_and_encodes_original(
    client_env, capsys: pytest.CaptureFixture
) -> None:
    draft_id = "55555555-5555-4555-8555-555555555555"
    forwarded_message = {
        "mail_version": "2.0",
        "message_id": "77777777-7777-4777-8777-777777777777",
        "reply_to": None,
        "sender": "user:alice@localhost",
        "recipients": ["sage@chorus@localhost"],
        "subject": "Fwd: Original subject",
        "body": "encoded",
        "tags": [],
        "sent_at": "2026-06-12T09:11:00+00:00",
        "metadata": {},
    }
    _, draft_route, send_route = _mock_forward_routes(draft_id, forwarded_message)

    cmd_forward(
        Namespace(
            output="text",
            message_id=ORIGINAL_ID,
            to=["sage@chorus@localhost"],
            note=None,
            subject=None,
            tags=[],
        )
    )

    # The draft defaults the subject to "Fwd: ..." and is NOT a reply.
    draft_body = json.loads(draft_route.calls[0].request.content)
    assert draft_body["subject"] == "Fwd: Original subject"
    assert draft_body["reply_to"] is None
    # The encoded body carries the original sender, recipients, and content.
    assert "---------- Forwarded message ----------" in draft_body["body"]
    assert f"From: {ORIGINAL_MESSAGE['sender']}" in draft_body["body"]
    assert "To: user:alice@localhost" in draft_body["body"]
    assert ORIGINAL_MESSAGE["body"] in draft_body["body"]
    # No note was supplied, so the body starts with the forwarded block.
    assert draft_body["body"].startswith("---------- Forwarded message ----------")

    # The forward is addressed to the user-specified recipient(s).
    send_body = json.loads(send_route.calls[0].request.content)
    assert send_body == {
        "recipients": ["sage@chorus@localhost"],
        "tags": [],
    }
    out = capsys.readouterr().out
    assert "Message Forwarded" in out


@respx.mock
def test_forward_honors_note_subject_and_tags(
    client_env, capsys: pytest.CaptureFixture
) -> None:
    draft_id = "55555555-5555-4555-8555-555555555555"
    forwarded_message = {
        "mail_version": "2.0",
        "message_id": "77777777-7777-4777-8777-777777777777",
        "reply_to": None,
        "sender": "user:alice@localhost",
        "recipients": ["sage@chorus@localhost", "philosopher@chorus@localhost"],
        "subject": "Custom subject",
        "body": "encoded",
        "tags": ["fyi", "project-x"],
        "sent_at": "2026-06-12T09:11:00+00:00",
        "metadata": {},
    }
    _, draft_route, send_route = _mock_forward_routes(draft_id, forwarded_message)

    cmd_forward(
        Namespace(
            output="text",
            message_id=ORIGINAL_ID,
            to=["sage@chorus@localhost", "philosopher@chorus@localhost"],
            note="Please take a look.",
            subject="Custom subject",
            tags=["fyi", "project-x"],
        )
    )

    draft_body = json.loads(draft_route.calls[0].request.content)
    assert draft_body["subject"] == "Custom subject"
    assert draft_body["tags"] == ["fyi", "project-x"]
    # The note is prepended above the forwarded block.
    assert draft_body["body"].startswith("Please take a look.\n\n")
    assert "---------- Forwarded message ----------" in draft_body["body"]

    send_body = json.loads(send_route.calls[0].request.content)
    assert send_body["recipients"] == [
        "sage@chorus@localhost",
        "philosopher@chorus@localhost",
    ]


@respx.mock
def test_forward_raises_when_original_missing(client_env) -> None:
    respx.get(f"{SERVER}/inbox/{ORIGINAL_ID}").mock(return_value=httpx.Response(404))
    with pytest.raises(RuntimeError, match="404"):
        cmd_forward(
            Namespace(
                output="text",
                message_id=ORIGINAL_ID,
                to=["sage@chorus@localhost"],
                note=None,
                subject=None,
                tags=[],
            )
        )
