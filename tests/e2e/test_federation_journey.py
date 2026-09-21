# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Charon Labs (contribution PR)

"""Real TLS/proxy, multi-node Federation v1 closure journey."""

from __future__ import annotations

import json
import sqlite3
from contextlib import ExitStack
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

import httpx
from mail_protocol.core.federation import MAILInterServerMessage
from mail_protocol.core.messages import MAILMessage
from mail_server.federation.keys import load_federation_private_key
from mail_server.federation.signatures import sign_federation_request


def _send(node: Any, token: str, subject: str, recipients: list[str]) -> str:
    draft = node.cli_json("compose", subject, "federation closure body", token=token)
    sent = node.cli_json(
        "send",
        draft["entry"]["draft"]["draft_id"],
        *recipients,
        token=token,
    )
    return sent["message"]["message_id"]


def _inbox_contains(node: Any, token: str, message_id: str) -> bool:
    result = node.cli("inbox", token=token)
    if result.returncode != 0:
        return False
    return any(
        entry["message_id"] == message_id
        for entry in json.loads(result.stdout)["entries"]
    )


def _outbox_delivered(node: Any, token: str, message_id: str) -> bool:
    result = node.cli("outbox-open", message_id, token=token)
    return result.returncode == 0 and (
        json.loads(result.stdout)["entry"]["delivered_at"] is not None
    )


def _outbound_rows(node: Any, message_id: str) -> list[tuple[str, str, int, dict]]:
    connection = sqlite3.connect(f"file:{node.database_path}?mode=ro", uri=True)
    try:
        rows = connection.execute(
            "SELECT envelope_id, status, body "
            "FROM federation_outbound WHERE message_id = ? ORDER BY destination_host",
            (message_id,),
        ).fetchall()
        parsed = [(envelope_id, status, json.loads(body)) for envelope_id, status, body in rows]
        return [
            (envelope_id, status, body["attempt_count"], body)
            for envelope_id, status, body in parsed
        ]
    finally:
        connection.close()


def _signed_old_key_request(
    *,
    origin: Any,
    destination: Any,
    old_key_path: Path,
    old_key_id: str,
) -> tuple[httpx.Response, str]:
    now = datetime.now(UTC)
    message_id = str(uuid4())
    message = MAILMessage(
        mail_version="2.0",
        message_id=message_id,
        sender=f"user:alice@{origin.public_host}",
        recipients=[f"user:bob@{destination.public_host}"],
        subject="Old overlap key",
        body="signed with the overlapping key",
        tags=["rotation"],
        sent_at=now,
        metadata={"rotation": True},
    )
    envelope = MAILInterServerMessage.model_validate(
        {
            "message_id": str(uuid4()),
            "sender_host": origin.public_host,
            "recipient_host": destination.public_host,
            "message": message,
            "metadata": {},
            "sent_at": now,
            "protocol_version": "1",
        },
        context={"defer_federation_host_checks": True},
    )
    signed = sign_federation_request(
        url=f"{destination.public_url}/daemon/deliver/remote/v1",
        envelope=envelope,
        signing_key=load_federation_private_key(old_key_path, key_id=old_key_id),
        created=now,
    )
    response = httpx.post(
        signed.url,
        headers=signed.headers,
        content=signed.body,
        verify=str(origin.env["MAIL_FEDERATION_CA_FILE"]),
        timeout=10,
    )
    return response, message_id


def _dsn_for(node: Any, token: str, original_message_id: str) -> list[dict]:
    inbox = node.cli_json("inbox", token=token)
    matches: list[dict] = []
    for entry in inbox["entries"]:
        opened = node.cli_json("inbox-open", entry["message_id"], token=token)
        message = opened["entry"]["message"]
        dsn = message["metadata"].get("dsn")
        if dsn and dsn["original_message_id"] == original_message_id:
            matches.append(dsn)
    return matches


def test_federation_tls_proxy_rotation_restart_and_dsn(federation_e2e_stack) -> None:
    stack = federation_e2e_stack
    a, b, c = (stack.nodes[name] for name in ("a", "b", "c"))
    alice_a = a.login("alice")
    bob_a = a.login("bob")
    bob_b = b.login("bob")
    bob_c = c.login("bob")

    # Discovery and delivery cross a real TLS listener with a private test CA.
    for node in (a, b, c):
        manifest = httpx.get(
            f"{node.public_url}/.well-known/mail-federation",
            verify=str(stack.ca_file),
        )
        assert manifest.status_code == 200
        assert manifest.json()["delivery_url"].startswith(node.public_url)

    # A -> B reaches durable 202. Killing B before its daemon runs must not lose it.
    first_id = _send(
        a,
        alice_a,
        "A to B",
        [f"user:bob@{b.public_host}"],
    )
    stack.wait_for(lambda: _outbox_delivered(a, alice_a, first_id))
    b.stop_server(kill=True)
    b.start_server()
    with b.daemon_running():
        stack.wait_for(lambda: _inbox_contains(b, bob_b, first_id))
    first_inbox = b.cli_json("inbox", token=bob_b)
    assert sum(item["message_id"] == first_id for item in first_inbox["entries"]) == 1

    # Reply B -> A over the same signed path.
    reply = b.cli_json("reply", first_id, "Reply across federation", token=bob_b)
    reply_id = reply["message"]["message_id"]
    stack.wait_for(lambda: _outbox_delivered(b, bob_b, reply_id))
    with a.daemon_running():
        stack.wait_for(lambda: _inbox_contains(a, alice_a, reply_id))

    # One canonical message fans out locally and to two remote destination hosts.
    mixed_id = _send(
        a,
        alice_a,
        "A plus B plus C",
        [
            f"user:bob@{a.public_host}",
            f"user:bob@{b.public_host}",
            f"user:bob@{c.public_host}",
        ],
    )
    with ExitStack() as daemons:
        for node in (a, b, c):
            daemons.enter_context(node.daemon_running())
        stack.wait_for(lambda: _inbox_contains(a, bob_a, mixed_id))
        stack.wait_for(lambda: _inbox_contains(b, bob_b, mixed_id))
        stack.wait_for(lambda: _inbox_contains(c, bob_c, mixed_id))
        stack.wait_for(lambda: _outbox_delivered(a, alice_a, mixed_id))
    rows = _outbound_rows(a, mixed_id)
    assert len(rows) == 2
    assert {row[3]["envelope"]["message"]["message_id"] for row in rows} == {
        mixed_id
    }
    assert {
        tuple(row[3]["envelope"]["message"]["recipients"]) for row in rows
    } == {
        (f"user:bob@{b.public_host}",),
        (f"user:bob@{c.public_host}",),
    }

    # B has A's old manifest cached. It refreshes for A's new key while the old
    # key remains valid during overlap, then rejects it once overlap and cache go.
    old_key_path, old_key_id = a.rotate_key_with_overlap()
    rotated_manifest = httpx.get(
        f"{a.public_url}/.well-known/mail-federation",
        verify=str(stack.ca_file),
    ).json()
    assert {key["key_id"] for key in rotated_manifest["public_keys"]} == {
        old_key_id,
        a.key_id,
    }
    rotated_id = _send(
        a,
        alice_a,
        "New active key",
        [f"user:bob@{b.public_host}"],
    )
    stack.wait_for(lambda: _outbox_delivered(a, alice_a, rotated_id))
    overlap_response, overlap_message_id = _signed_old_key_request(
        origin=a,
        destination=b,
        old_key_path=old_key_path,
        old_key_id=old_key_id,
    )
    assert overlap_response.status_code == 202, overlap_response.text
    with b.daemon_running():
        stack.wait_for(lambda: _inbox_contains(b, bob_b, overlap_message_id))
    a.remove_key_overlap()
    b.restart_server()  # Clear B's valid overlap cache before checking revocation.
    rejected, _ = _signed_old_key_request(
        origin=a,
        destination=b,
        old_key_path=old_key_path,
        old_key_id=old_key_id,
    )
    assert rejected.status_code == 401

    # Persist a failed attempt, kill the origin, and prove the same envelope resumes.
    c.stop_server()
    restart_id = _send(
        a,
        alice_a,
        "Resume after origin crash",
        [f"user:bob@{c.public_host}"],
    )
    stack.wait_for(
        lambda: bool(_outbound_rows(a, restart_id))
        and _outbound_rows(a, restart_id)[0][2] >= 1
    )
    envelope_before = _outbound_rows(a, restart_id)[0][0]
    a.stop_server(kill=True)
    c.start_server()
    a.start_server()
    stack.wait_for(lambda: _outbox_delivered(a, alice_a, restart_id))
    assert _outbound_rows(a, restart_id)[0][0] == envelope_before
    with c.daemon_running():
        stack.wait_for(lambda: _inbox_contains(c, bob_c, restart_id))

    # Accelerate the exact six-attempt ladder and verify one structured local DSN.
    a.env["MAIL_FEDERATION_TEST_RETRY_DELAYS_SECONDS"] = "0.1,0.1,0.1,0.1,0.1"
    a.restart_server()
    failed_id = _send(
        a,
        alice_a,
        "Expected terminal failure",
        ["user:nobody@127.0.0.9"],
    )
    stack.wait_for(
        lambda: bool(_outbound_rows(a, failed_id))
        and _outbound_rows(a, failed_id)[0][1] == "dead_letter"
    )
    assert _outbound_rows(a, failed_id)[0][2] == 6
    with a.daemon_running():
        stack.wait_for(lambda: len(_dsn_for(a, alice_a, failed_id)) == 1)
    dsns = _dsn_for(a, alice_a, failed_id)
    assert len(dsns) == 1
    assert dsns[0]["attempt_count"] == 6
    assert len(dsns[0]["attempt_timestamps"]) == 6
