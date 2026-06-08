# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Charon Labs (contribution PR)

import os
from datetime import UTC, datetime
from pathlib import Path

# mail_server.auth checks MAIL_JWT_* env vars at import time. The
# values are inert for these tests; set placeholders so the auth
# module can be imported.
os.environ.setdefault("MAIL_JWT_SECRET_KEY", "test-secret-not-used")
os.environ.setdefault("MAIL_JWT_ALGORITHM", "HS256")

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from mail_protocol.core.lists import MAILListInBackend, MAILListPolicy
from mail_protocol.core.user_agents import (
    MAILAdmin,
    MAILUser,
    MAILUserAgent,
)
from mail_server import auth as mail_auth  # noqa: E402
from mail_server.backends.memory import fs as memory_fs  # noqa: E402
from mail_server.backends.memory.api import MemoryBackend  # noqa: E402
from mail_server.routers import lists as lists_router  # noqa: E402

ADMIN_ADDRESS = "admin:ryan@localhost"
USER_ADDRESS = "user:ryan@localhost"
OTHER_USER_ADDRESS = "user:alice@localhost"


@pytest.fixture
def deployment_dir(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> Path:
    deployment = tmp_path / "deployment"
    for subdir in (
        "user_agents",
        "swarms",
        "messages",
        "inbox_entries",
        "inboxes",
        "outbox_entries",
        "outboxes",
        "draft_entries",
        "drafts",
        "trash_entries",
        "trashes",
        "webhooks",
        "lists",
    ):
        (deployment / subdir).mkdir(parents=True, exist_ok=True)
    (deployment / "message_buffer.lock").touch()
    monkeypatch.setattr(memory_fs, "DEPLOYMENT_PATH", deployment)
    return deployment


def _admin_user_agent() -> MAILUserAgent:
    return MAILUserAgent(
        user_agent=MAILAdmin(
            ua_type="admin",
            admin_id="ryan",
            host="localhost",
        )
    )


def _regular_user_agent() -> MAILUserAgent:
    return MAILUserAgent(
        user_agent=MAILUser(
            ua_type="user",
            user_id="ryan",
            host="localhost",
        )
    )


def _other_user_agent() -> MAILUserAgent:
    return MAILUserAgent(
        user_agent=MAILUser(
            ua_type="user",
            user_id="alice",
            host="localhost",
        )
    )


@pytest.fixture
async def backend(deployment_dir: Path) -> MemoryBackend:
    instance = MemoryBackend()
    await instance.on_server_startup(host="localhost")
    return instance


@pytest.fixture
def client(
    backend: MemoryBackend,
    monkeypatch: pytest.MonkeyPatch,
    request: pytest.FixtureRequest,
) -> TestClient:
    """
    Build a FastAPI app wired with the lists routers only, with the
    auth functions monkeypatched to recognize three headers:

    - ``Authorization: Bearer admin`` → admin
    - ``Authorization: Bearer user`` → MAIL user
    - ``Authorization: Bearer alice`` → a second MAIL user

    Anything else returns 401 via the real validators' shape.
    """
    app = FastAPI()
    app.state.backend = backend
    app.include_router(lists_router.admin_router)
    app.include_router(lists_router.public_router)

    async def fake_validate_user_agent(
        *, backend: MemoryBackend, request_: object = None, **_: object
    ) -> MAILUserAgent:
        from fastapi import HTTPException, Request

        # The router signature passes ``request`` positionally; pull it
        # from kwargs to keep this signature flexible.
        actual_request: Request = request_  # type: ignore[assignment]
        token = actual_request.headers.get("Authorization", "")
        bearer = token.removeprefix("Bearer ").strip()
        match bearer:
            case "admin":
                return _admin_user_agent()
            case "user":
                return _regular_user_agent()
            case "alice":
                return _other_user_agent()
            case _:
                raise HTTPException(status_code=401, detail="unauthorized")

    async def fake_validate_admin(
        *, backend: MemoryBackend, request_: object = None, **_: object
    ) -> MAILAdmin:
        from fastapi import HTTPException

        user_agent = await fake_validate_user_agent(
            backend=backend, request_=request_
        )
        if not isinstance(user_agent.user_agent, MAILAdmin):
            raise HTTPException(status_code=401, detail="not admin")
        return user_agent.user_agent

    # The router does ``await validate_admin(backend=backend, request=request)``.
    # Patch the auth module attributes so the router resolves to our fakes
    # via the module-level lookup chain.
    monkeypatch.setattr(
        lists_router,
        "validate_admin",
        lambda backend, request: fake_validate_admin(
            backend=backend, request_=request
        ),
    )
    monkeypatch.setattr(
        lists_router,
        "validate_user_agent",
        lambda backend, request: fake_validate_user_agent(
            backend=backend, request_=request
        ),
    )

    return TestClient(app)


def _admin_headers() -> dict[str, str]:
    return {"Authorization": "Bearer admin"}


def _user_headers() -> dict[str, str]:
    return {"Authorization": "Bearer user"}


def _other_headers() -> dict[str, str]:
    return {"Authorization": "Bearer alice"}


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


def _seed_list(backend: MemoryBackend, *, members: list[str] | None = None) -> str:
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
    backend.lists[record.get_address()] = record
    return record.get_address()


# ─── Admin endpoints ───────────────────────────────────────────────


def test_admin_post_list_creates(client: TestClient) -> None:
    response = client.post(
        "/admin/lists",
        json=_make_post_body(),
        headers=_admin_headers(),
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["mail_list"]["name"] == "welfare-discourse"
    assert payload["mail_list"]["swarm"] == "chorus"
    assert payload["mail_list"]["host"] == "localhost"
    assert "list_id" in payload["mail_list"]


def test_admin_post_list_rejects_unsupported_policy(
    client: TestClient,
) -> None:
    response = client.post(
        "/admin/lists",
        json=_make_post_body(
            policy=MAILListPolicy(visibility="private"),
        ),
        headers=_admin_headers(),
    )
    assert response.status_code == 501
    assert "private" in response.text


def test_admin_post_list_rejects_closed_join_policy(
    client: TestClient,
) -> None:
    response = client.post(
        "/admin/lists",
        json=_make_post_body(
            policy=MAILListPolicy(join_policy="approval"),
        ),
        headers=_admin_headers(),
    )
    assert response.status_code == 501


def test_admin_post_list_rejects_closed_send_policy(
    client: TestClient,
) -> None:
    response = client.post(
        "/admin/lists",
        json=_make_post_body(
            policy=MAILListPolicy(send_policy="members-only"),
        ),
        headers=_admin_headers(),
    )
    assert response.status_code == 501


def test_admin_post_list_duplicate_returns_409(client: TestClient) -> None:
    client.post(
        "/admin/lists",
        json=_make_post_body(),
        headers=_admin_headers(),
    )
    response = client.post(
        "/admin/lists",
        json=_make_post_body(),
        headers=_admin_headers(),
    )
    assert response.status_code == 409


def test_admin_get_lists_returns_all(
    client: TestClient,
    backend: MemoryBackend,
) -> None:
    _seed_list(backend)
    response = client.get("/admin/lists", headers=_admin_headers())
    assert response.status_code == 200
    assert len(response.json()["lists"]) == 1


def test_admin_get_list_returns_specific(
    client: TestClient,
    backend: MemoryBackend,
) -> None:
    address = _seed_list(backend)
    response = client.get(f"/admin/lists/{address}", headers=_admin_headers())
    assert response.status_code == 200
    assert response.json()["mail_list"]["name"] == "welfare-discourse"


def test_admin_get_list_missing_returns_404(client: TestClient) -> None:
    response = client.get(
        "/admin/lists/list:nonexistent@chorus@localhost",
        headers=_admin_headers(),
    )
    assert response.status_code == 404


def test_admin_patch_list_updates_policy_no_op_for_open(
    client: TestClient,
    backend: MemoryBackend,
) -> None:
    address = _seed_list(backend)
    response = client.patch(
        f"/admin/lists/{address}",
        json={"policy": MAILListPolicy().model_dump()},
        headers=_admin_headers(),
    )
    assert response.status_code == 200


def test_admin_patch_list_rejects_closed_policy(
    client: TestClient,
    backend: MemoryBackend,
) -> None:
    address = _seed_list(backend)
    response = client.patch(
        f"/admin/lists/{address}",
        json={"policy": MAILListPolicy(visibility="private").model_dump()},
        headers=_admin_headers(),
    )
    assert response.status_code == 501


def test_admin_delete_list_removes(
    client: TestClient,
    backend: MemoryBackend,
) -> None:
    address = _seed_list(backend)
    response = client.delete(f"/admin/lists/{address}", headers=_admin_headers())
    assert response.status_code == 200
    assert address not in backend.lists


def test_admin_delete_list_missing_returns_404(client: TestClient) -> None:
    response = client.delete(
        "/admin/lists/list:nonexistent@chorus@localhost",
        headers=_admin_headers(),
    )
    assert response.status_code == 404


def test_admin_add_member(
    client: TestClient,
    backend: MemoryBackend,
) -> None:
    address = _seed_list(backend)
    response = client.post(
        f"/admin/lists/{address}/members",
        json={"member_address": "philosopher@chorus@localhost"},
        headers=_admin_headers(),
    )
    assert response.status_code == 200
    assert "philosopher@chorus@localhost" in response.json()["mail_list"]["members"]


def test_admin_remove_member(
    client: TestClient,
    backend: MemoryBackend,
) -> None:
    address = _seed_list(
        backend,
        members=["philosopher@chorus@localhost"],
    )
    response = client.delete(
        f"/admin/lists/{address}/members/philosopher@chorus@localhost",
        headers=_admin_headers(),
    )
    assert response.status_code == 200
    assert backend.lists[address].members == []


# ─── Public endpoints ──────────────────────────────────────────────


def test_get_lists_requires_auth(client: TestClient) -> None:
    response = client.get("/lists")
    assert response.status_code == 401


def test_get_lists_returns_visible_lists(
    client: TestClient,
    backend: MemoryBackend,
) -> None:
    _seed_list(backend)
    response = client.get("/lists", headers=_user_headers())
    assert response.status_code == 200
    assert len(response.json()["lists"]) == 1


def test_get_list_specific(
    client: TestClient,
    backend: MemoryBackend,
) -> None:
    address = _seed_list(backend)
    response = client.get(f"/lists/{address}", headers=_user_headers())
    assert response.status_code == 200
    assert response.json()["mail_list"]["name"] == "welfare-discourse"


def test_get_list_missing_returns_404(client: TestClient) -> None:
    response = client.get(
        "/lists/list:nonexistent@chorus@localhost",
        headers=_user_headers(),
    )
    assert response.status_code == 404


def test_subscribe_self(
    client: TestClient,
    backend: MemoryBackend,
) -> None:
    address = _seed_list(backend)
    response = client.post(
        f"/lists/{address}/members",
        json={"member_address": USER_ADDRESS},
        headers=_user_headers(),
    )
    assert response.status_code == 200
    assert USER_ADDRESS in backend.lists[address].members


def test_subscribe_other_rejected_with_403(
    client: TestClient,
    backend: MemoryBackend,
) -> None:
    address = _seed_list(backend)
    response = client.post(
        f"/lists/{address}/members",
        json={"member_address": OTHER_USER_ADDRESS},
        headers=_user_headers(),
    )
    assert response.status_code == 403


def test_subscribe_missing_list_returns_404(client: TestClient) -> None:
    response = client.post(
        "/lists/list:nonexistent@chorus@localhost/members",
        json={"member_address": USER_ADDRESS},
        headers=_user_headers(),
    )
    assert response.status_code == 404


def test_unsubscribe_self(
    client: TestClient,
    backend: MemoryBackend,
) -> None:
    address = _seed_list(
        backend,
        members=[USER_ADDRESS, OTHER_USER_ADDRESS],
    )
    response = client.delete(
        f"/lists/{address}/members/{USER_ADDRESS}",
        headers=_user_headers(),
    )
    assert response.status_code == 200
    assert USER_ADDRESS not in backend.lists[address].members
    assert OTHER_USER_ADDRESS in backend.lists[address].members


def test_unsubscribe_other_rejected_with_403(
    client: TestClient,
    backend: MemoryBackend,
) -> None:
    address = _seed_list(
        backend,
        members=[USER_ADDRESS, OTHER_USER_ADDRESS],
    )
    response = client.delete(
        f"/lists/{address}/members/{OTHER_USER_ADDRESS}",
        headers=_user_headers(),
    )
    assert response.status_code == 403


_ = mail_auth  # silence the import-for-side-effect note
