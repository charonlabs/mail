# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Charon Labs (contribution PR)

"""
Executable checklist of the endpoints that are still NotImplementedError
stubs (docs/testing-plan.md §5, Phase 1).

Each test asserts the *intended* behavior and is marked strict-xfail on
the NotImplementedError the stub currently raises. When a stub gets
implemented, its test XPASSes (a strict failure) — replace it with real
coverage at that point.
"""

import pytest
from fastapi.testclient import TestClient

USER = "user:alice@localhost"
DAEMON = "daemon:dummy@localhost"

stub = pytest.mark.xfail(
    raises=NotImplementedError,
    strict=True,
    reason="endpoint is a NotImplementedError stub",
)


@stub
def test_delete_inbox_message_moves_to_trash(
    app_client: TestClient, headers_for, deliver_message
) -> None:
    message_id = deliver_message(USER, ["user:bob@localhost"])
    response = app_client.delete(
        f"/inbox/{message_id}", headers=headers_for("user:bob@localhost")
    )
    assert response.status_code == 200


@stub
def test_delete_draft_removes_it(app_client: TestClient, headers_for) -> None:
    headers = headers_for(USER)
    response = app_client.post(
        "/drafts/",
        json={"subject": "Disposable", "body": "Delete me"},
        headers=headers,
    )
    draft_id = response.json()["entry"]["draft"]["draft_id"]
    response = app_client.delete(f"/drafts/{draft_id}", headers=headers)
    assert response.status_code == 200


@stub
def test_delete_trashed_message_removes_it(
    app_client: TestClient, headers_for
) -> None:
    response = app_client.delete(
        "/trash/11111111-1111-4111-8111-111111111111",
        headers=headers_for(USER),
    )
    assert response.status_code in (200, 404)


@stub
def test_trash_clear_empties_box(app_client: TestClient, headers_for) -> None:
    response = app_client.post("/trash/clear", headers=headers_for(USER))
    assert response.status_code == 200


@stub
def test_patch_webhook_updates(app_client: TestClient, headers_for) -> None:
    headers = headers_for("admin:ryan@localhost")
    response = app_client.post(
        "/admin/webhooks",
        json={
            "url": "https://example.com/mail-events",
            "events": ["mail.delivered"],
            "secret": "shhh",
        },
        headers=headers,
    )
    webhook_id = response.json()["webhook"]["webhook_id"]
    response = app_client.patch(
        f"/admin/webhooks/{webhook_id}",
        json={"url": "https://example.com/elsewhere", "secret": "new-secret"},
        headers=headers,
    )
    assert response.status_code == 200


@stub
def test_daemon_deliver_remote(app_client: TestClient, headers_for) -> None:
    response = app_client.post(
        "/daemon/deliver/remote",
        json={"messages": []},
        headers=headers_for(DAEMON),
    )
    assert response.status_code == 200
