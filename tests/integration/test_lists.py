# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Charon Labs (contribution PR)

"""
Lists router behavior over the real app with real JWT auth.

Migrated from tests/unit/test_mail_lists_endpoints.py, which wired a
minimal app with monkeypatched auth; the assertions are unchanged.
"""

from collections.abc import Callable
from datetime import UTC, datetime

from fastapi.testclient import TestClient
from mail_protocol.core.lists import MAILListInBackend, MAILListPolicy

ADMIN_ADDRESS = "admin:ryan@localhost"
USER_ADDRESS = "user:alice@localhost"
OTHER_USER_ADDRESS = "user:bob@localhost"


def _make_post_body(
    *,
    members: list[str] | None = None,
    policy: MAILListPolicy | None = None,
) -> dict[str, object]:
    body: dict[str, object] = {
        "name": "welfare-discourse",
        "swarm_name": "chorus",
        "owner": ADMIN_ADDRESS,
        "members": members or [],
    }
    if policy is not None:
        body["policy"] = policy.model_dump()
    return body


def _seed_list(
    seed_list: Callable[[MAILListInBackend], str],
    *,
    members: list[str] | None = None,
) -> str:
    now = datetime(2026, 6, 4, 0, 0, tzinfo=UTC)
    record = MAILListInBackend(
        name="welfare-discourse",
        swarm="chorus",
        host="localhost",
        owner=ADMIN_ADDRESS,
        members=members or [],
        policy=MAILListPolicy(),
        list_id="11111111-1111-1111-1111-111111111111",
        created_at=now,
        updated_at=now,
    )
    return seed_list(record)


# ─── Admin endpoints ───────────────────────────────────────────────


def test_admin_post_list_creates(app_client: TestClient, headers_for) -> None:
    response = app_client.post(
        "/admin/lists",
        json=_make_post_body(),
        headers=headers_for(ADMIN_ADDRESS),
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["mail_list"]["name"] == "welfare-discourse"
    assert payload["mail_list"]["swarm"] == "chorus"
    assert payload["mail_list"]["host"] == "localhost"
    assert "list_id" in payload["mail_list"]


def test_admin_post_list_rejects_unsupported_policy(
    app_client: TestClient, headers_for
) -> None:
    response = app_client.post(
        "/admin/lists",
        json=_make_post_body(policy=MAILListPolicy(visibility="private")),
        headers=headers_for(ADMIN_ADDRESS),
    )
    assert response.status_code == 501
    assert "private" in response.text


def test_admin_post_list_rejects_closed_join_policy(
    app_client: TestClient, headers_for
) -> None:
    response = app_client.post(
        "/admin/lists",
        json=_make_post_body(policy=MAILListPolicy(join_policy="approval")),
        headers=headers_for(ADMIN_ADDRESS),
    )
    assert response.status_code == 501


def test_admin_post_list_rejects_closed_send_policy(
    app_client: TestClient, headers_for
) -> None:
    response = app_client.post(
        "/admin/lists",
        json=_make_post_body(policy=MAILListPolicy(send_policy="members-only")),
        headers=headers_for(ADMIN_ADDRESS),
    )
    assert response.status_code == 501


def test_admin_post_list_duplicate_returns_409(
    app_client: TestClient, headers_for
) -> None:
    headers = headers_for(ADMIN_ADDRESS)
    app_client.post("/admin/lists", json=_make_post_body(), headers=headers)
    response = app_client.post(
        "/admin/lists", json=_make_post_body(), headers=headers
    )
    assert response.status_code == 409


def test_admin_get_lists_returns_all(
    app_client: TestClient,
    headers_for,
    seed_list: Callable[[MAILListInBackend], str],
) -> None:
    _seed_list(seed_list)
    response = app_client.get("/admin/lists", headers=headers_for(ADMIN_ADDRESS))
    assert response.status_code == 200
    assert len(response.json()["lists"]) == 1


def test_admin_get_list_returns_specific(
    app_client: TestClient,
    headers_for,
    seed_list: Callable[[MAILListInBackend], str],
) -> None:
    address = _seed_list(seed_list)
    response = app_client.get(
        f"/admin/lists/{address}", headers=headers_for(ADMIN_ADDRESS)
    )
    assert response.status_code == 200
    assert response.json()["mail_list"]["name"] == "welfare-discourse"


def test_admin_get_list_missing_returns_404(
    app_client: TestClient, headers_for
) -> None:
    response = app_client.get(
        "/admin/lists/nonexistent@chorus",
        headers=headers_for(ADMIN_ADDRESS),
    )
    assert response.status_code == 404


def test_admin_get_list_malformed_local_address_returns_422(
    app_client: TestClient, headers_for
) -> None:
    # The full ``list:`` address is no longer accepted here — the path
    # param is the list's local address (name@swarm).
    response = app_client.get(
        "/admin/lists/list:welfare-discourse@chorus@localhost",
        headers=headers_for(ADMIN_ADDRESS),
    )
    assert response.status_code == 422


def test_admin_patch_list_updates_policy_no_op_for_open(
    app_client: TestClient,
    headers_for,
    seed_list: Callable[[MAILListInBackend], str],
) -> None:
    address = _seed_list(seed_list)
    response = app_client.patch(
        f"/admin/lists/{address}",
        json={"policy": MAILListPolicy().model_dump()},
        headers=headers_for(ADMIN_ADDRESS),
    )
    assert response.status_code == 200


def test_admin_patch_list_rejects_closed_policy(
    app_client: TestClient,
    headers_for,
    seed_list: Callable[[MAILListInBackend], str],
) -> None:
    address = _seed_list(seed_list)
    response = app_client.patch(
        f"/admin/lists/{address}",
        json={"policy": MAILListPolicy(visibility="private").model_dump()},
        headers=headers_for(ADMIN_ADDRESS),
    )
    assert response.status_code == 501


def test_admin_delete_list_removes(
    app_client: TestClient,
    headers_for,
    seed_list: Callable[[MAILListInBackend], str],
) -> None:
    address = _seed_list(seed_list)
    response = app_client.delete(
        f"/admin/lists/{address}", headers=headers_for(ADMIN_ADDRESS)
    )
    assert response.status_code == 200
    # The list is gone: a follow-up read 404s.
    assert (
        app_client.get(
            f"/lists/{address}", headers=headers_for(ADMIN_ADDRESS)
        ).status_code
        == 404
    )


def test_admin_delete_list_missing_returns_404(
    app_client: TestClient, headers_for
) -> None:
    response = app_client.delete(
        "/admin/lists/nonexistent@chorus",
        headers=headers_for(ADMIN_ADDRESS),
    )
    assert response.status_code == 404


def test_admin_add_member(
    app_client: TestClient,
    headers_for,
    seed_list: Callable[[MAILListInBackend], str],
) -> None:
    address = _seed_list(seed_list)
    response = app_client.post(
        f"/admin/lists/{address}/members",
        json={"member_address": "philosopher@chorus@localhost"},
        headers=headers_for(ADMIN_ADDRESS),
    )
    assert response.status_code == 200
    assert "philosopher@chorus@localhost" in response.json()["mail_list"]["members"]


def test_admin_remove_member(
    app_client: TestClient,
    headers_for,
    seed_list: Callable[[MAILListInBackend], str],
    list_members: Callable[..., list[str]],
) -> None:
    address = _seed_list(seed_list, members=["philosopher@chorus@localhost"])
    response = app_client.delete(
        f"/admin/lists/{address}/members/philosopher@chorus@localhost",
        headers=headers_for(ADMIN_ADDRESS),
    )
    assert response.status_code == 200
    assert list_members(address) == []


def test_admin_lists_reject_non_admin(
    app_client: TestClient,
    headers_for,
    seed_list: Callable[[MAILListInBackend], str],
) -> None:
    _seed_list(seed_list)
    response = app_client.get(
        "/admin/lists", headers=headers_for(USER_ADDRESS)
    )
    assert response.status_code == 401


# ─── Public endpoints ──────────────────────────────────────────────


def test_get_lists_requires_auth(app_client: TestClient) -> None:
    response = app_client.get("/lists")
    assert response.status_code == 401


def test_get_lists_returns_visible_lists(
    app_client: TestClient,
    headers_for,
    seed_list: Callable[[MAILListInBackend], str],
) -> None:
    _seed_list(seed_list)
    response = app_client.get("/lists", headers=headers_for(USER_ADDRESS))
    assert response.status_code == 200
    assert len(response.json()["lists"]) == 1


def test_get_list_specific(
    app_client: TestClient,
    headers_for,
    seed_list: Callable[[MAILListInBackend], str],
) -> None:
    address = _seed_list(seed_list)
    response = app_client.get(
        f"/lists/{address}", headers=headers_for(USER_ADDRESS)
    )
    assert response.status_code == 200
    assert response.json()["mail_list"]["name"] == "welfare-discourse"


def test_get_list_missing_returns_404(
    app_client: TestClient, headers_for
) -> None:
    response = app_client.get(
        "/lists/nonexistent@chorus",
        headers=headers_for(USER_ADDRESS),
    )
    assert response.status_code == 404


def test_subscribe_self(
    app_client: TestClient,
    headers_for,
    seed_list: Callable[[MAILListInBackend], str],
    list_members: Callable[..., list[str]],
) -> None:
    address = _seed_list(seed_list)
    response = app_client.post(
        f"/lists/{address}/subscribe", headers=headers_for(USER_ADDRESS)
    )
    assert response.status_code == 200
    assert USER_ADDRESS in list_members(address)


def test_subscribe_ignores_supplied_member_address(
    app_client: TestClient,
    headers_for,
    seed_list: Callable[[MAILListInBackend], str],
    list_members: Callable[..., list[str]],
) -> None:
    """
    Subscribe is body-less: only the authenticated caller is ever
    subscribed, so a request body naming another user-agent must have
    no effect on the member list.
    """

    address = _seed_list(seed_list)
    response = app_client.post(
        f"/lists/{address}/subscribe",
        json={"member_address": OTHER_USER_ADDRESS},
        headers=headers_for(USER_ADDRESS),
    )
    assert response.status_code == 200
    members = list_members(address)
    assert USER_ADDRESS in members
    assert OTHER_USER_ADDRESS not in members


def test_subscribe_missing_list_returns_404(
    app_client: TestClient, headers_for
) -> None:
    response = app_client.post(
        "/lists/nonexistent@chorus/subscribe",
        headers=headers_for(USER_ADDRESS),
    )
    assert response.status_code == 404


def test_unsubscribe_self(
    app_client: TestClient,
    headers_for,
    seed_list: Callable[[MAILListInBackend], str],
    list_members: Callable[..., list[str]],
) -> None:
    address = _seed_list(seed_list, members=[USER_ADDRESS, OTHER_USER_ADDRESS])
    response = app_client.post(
        f"/lists/{address}/unsubscribe", headers=headers_for(USER_ADDRESS)
    )
    assert response.status_code == 200
    members = list_members(address)
    assert USER_ADDRESS not in members
    assert OTHER_USER_ADDRESS in members


def test_unsubscribe_uses_authenticated_user(
    app_client: TestClient,
    headers_for,
    seed_list: Callable[[MAILListInBackend], str],
    list_members: Callable[..., list[str]],
) -> None:
    address = _seed_list(seed_list, members=[USER_ADDRESS, OTHER_USER_ADDRESS])
    response = app_client.post(
        f"/lists/{address}/unsubscribe", headers=headers_for(OTHER_USER_ADDRESS)
    )
    assert response.status_code == 200
    members = list_members(address)
    assert USER_ADDRESS in members
    assert OTHER_USER_ADDRESS not in members
