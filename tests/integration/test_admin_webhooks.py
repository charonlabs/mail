# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Charon Labs (contribution PR)

import pytest
from fastapi.testclient import TestClient

ADMIN = "admin:ryan@localhost"

WEBHOOK_BODY = {
    "url": "https://example.com/mail-events",
    "events": ["mail.delivered"],
    "secret": "shhh",
}


def _post_webhook(client: TestClient, headers: dict[str, str]) -> str:
    response = client.post("/admin/webhooks", json=WEBHOOK_BODY, headers=headers)
    assert response.status_code == 200, response.text
    return response.json()["webhook"]["webhook_id"]


def test_post_webhook_creates(app_client: TestClient, headers_for) -> None:
    headers = headers_for(ADMIN)
    webhook_id = _post_webhook(app_client, headers)
    assert webhook_id.startswith("wh_")

    response = app_client.get("/admin/webhooks", headers=headers)
    assert response.status_code == 200
    assert response.json()["webhook_ids"] == [webhook_id]


def test_post_webhook_duplicate_url_returns_existing(
    app_client: TestClient, headers_for
) -> None:
    headers = headers_for(ADMIN)
    first_id = _post_webhook(app_client, headers)
    second_id = _post_webhook(app_client, headers)
    assert first_id == second_id


def test_post_webhook_invalid_event_returns_422(
    app_client: TestClient, headers_for
) -> None:
    response = app_client.post(
        "/admin/webhooks",
        json={**WEBHOOK_BODY, "events": ["mail.exploded"]},
        headers=headers_for(ADMIN),
    )
    assert response.status_code == 422


def test_get_webhook_by_id(app_client: TestClient, headers_for) -> None:
    headers = headers_for(ADMIN)
    webhook_id = _post_webhook(app_client, headers)
    response = app_client.get(f"/admin/webhooks/{webhook_id}", headers=headers)
    assert response.status_code == 200
    assert response.json()["webhook"]["url"] == WEBHOOK_BODY["url"]


@pytest.mark.xfail(
    raises=ValueError,
    strict=True,
    reason=(
        "BUG: routers/admin.get_webhook does not catch the backend's "
        "ValueError for an unknown webhook ID (500). Should be 404."
    ),
)
def test_get_webhook_unknown_returns_404(
    app_client: TestClient, headers_for
) -> None:
    response = app_client.get(
        "/admin/webhooks/wh_nonexistent", headers=headers_for(ADMIN)
    )
    assert response.status_code == 404


def test_delete_webhook_removes(app_client: TestClient, headers_for) -> None:
    headers = headers_for(ADMIN)
    webhook_id = _post_webhook(app_client, headers)
    response = app_client.delete(
        f"/admin/webhooks/{webhook_id}", headers=headers
    )
    assert response.status_code == 200

    response = app_client.get("/admin/webhooks", headers=headers)
    assert response.json()["webhook_ids"] == []


@pytest.mark.xfail(
    raises=ValueError,
    strict=True,
    reason=(
        "BUG: routers/admin.delete_webhook does not catch the backend's "
        "ValueError for an unknown webhook ID (500). Should be 404."
    ),
)
def test_delete_webhook_unknown_returns_404(
    app_client: TestClient, headers_for
) -> None:
    response = app_client.delete(
        "/admin/webhooks/wh_nonexistent", headers=headers_for(ADMIN)
    )
    assert response.status_code == 404


@pytest.mark.xfail(
    raises=TypeError,
    strict=True,
    reason=(
        "BUG: routers/admin.patch_webhook calls backend.admin_webhook_get "
        "with a payload kwarg instead of backend.admin_webhook_patch "
        "(which is itself still a NotImplementedError stub)."
    ),
)
def test_patch_webhook_updates(app_client: TestClient, headers_for) -> None:
    headers = headers_for(ADMIN)
    webhook_id = _post_webhook(app_client, headers)
    response = app_client.patch(
        f"/admin/webhooks/{webhook_id}",
        json={"url": "https://example.com/elsewhere", "secret": "new-secret"},
        headers=headers,
    )
    assert response.status_code == 200
