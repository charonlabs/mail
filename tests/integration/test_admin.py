# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Charon Labs (contribution PR)

from fastapi.testclient import TestClient

ADMIN = "admin:ryan@localhost"
SWARM = "chorus"


# ─── Agents ────────────────────────────────────────────────────────


def test_get_agents_lists_local_addresses(app_client: TestClient, headers_for) -> None:
    response = app_client.get("/admin/agents", headers=headers_for(ADMIN))
    assert response.status_code == 200
    assert response.json()["agents"] == [f"sage@{SWARM}"]


def test_get_agent_by_local_address(app_client: TestClient, headers_for) -> None:
    response = app_client.get(f"/admin/agents/sage@{SWARM}", headers=headers_for(ADMIN))
    assert response.status_code == 200
    assert response.json()["agent"]["name"] == "sage"


def test_get_agent_unknown_returns_404(app_client: TestClient, headers_for) -> None:
    response = app_client.get(
        f"/admin/agents/ghost@{SWARM}", headers=headers_for(ADMIN)
    )
    assert response.status_code == 404


def test_get_agent_malformed_local_address_returns_422(
    app_client: TestClient, headers_for
) -> None:
    # A full address (name@swarm@host) is no longer accepted here: the
    # path param is the *local* address (name@swarm).
    response = app_client.get(
        f"/admin/agents/sage@{SWARM}@localhost", headers=headers_for(ADMIN)
    )
    assert response.status_code == 422


def test_get_agent_non_slug_returns_422(app_client: TestClient, headers_for) -> None:
    response = app_client.get(
        f"/admin/agents/Sage@{SWARM}", headers=headers_for(ADMIN)
    )
    assert response.status_code == 422


def test_post_agent_creates_and_can_login(
    app_client: TestClient, headers_for, token_for
) -> None:
    response = app_client.post(
        "/admin/agents",
        json={
            "agent_name": "muse",
            "swarm_name": SWARM,
            "agent_password": "muse-password",
        },
        headers=headers_for(ADMIN),
    )
    assert response.status_code == 200
    assert response.json()["agent"]["name"] == "muse"

    # The new agent authenticates and has a working (empty) inbox.
    headers = headers_for(f"muse@{SWARM}@localhost", password="muse-password")
    response = app_client.get("/inbox", headers=headers)
    assert response.status_code == 200
    assert response.json()["entries"] == []


def test_post_agent_duplicate_returns_409(app_client: TestClient, headers_for) -> None:
    response = app_client.post(
        "/admin/agents",
        json={
            "agent_name": "sage",
            "swarm_name": SWARM,
            "agent_password": "irrelevant",
        },
        headers=headers_for(ADMIN),
    )
    assert response.status_code == 409


def test_post_agent_invalid_name_returns_422(
    app_client: TestClient, headers_for
) -> None:
    response = app_client.post(
        "/admin/agents",
        json={
            "agent_name": "Not A Slug!",
            "swarm_name": SWARM,
            "agent_password": "irrelevant",
        },
        headers=headers_for(ADMIN),
    )
    assert response.status_code == 422


def test_delete_agent_removes_account_and_boxes(
    app_client: TestClient, headers_for
) -> None:
    address = f"sage@{SWARM}@localhost"
    response = app_client.delete(
        f"/admin/agents/sage@{SWARM}", headers=headers_for(ADMIN)
    )
    assert response.status_code == 200
    # The account is gone: a follow-up admin read 404s.
    assert (
        app_client.get(
            f"/admin/agents/sage@{SWARM}", headers=headers_for(ADMIN)
        ).status_code
        == 404
    )

    # Credentials no longer authenticate.
    response = app_client.post(
        "/auth/token",
        data={"username": address, "password": "correct-horse-battery-staple"},
    )
    assert response.status_code == 401


def test_delete_agent_unknown_returns_404(app_client: TestClient, headers_for) -> None:
    response = app_client.delete(
        f"/admin/agents/ghost@{SWARM}", headers=headers_for(ADMIN)
    )
    assert response.status_code == 404


# ─── Daemons ───────────────────────────────────────────────────────


def test_get_daemons_lists_worker_names(app_client: TestClient, headers_for) -> None:
    response = app_client.get("/admin/daemons", headers=headers_for(ADMIN))
    assert response.status_code == 200
    assert response.json()["daemons"] == ["dummy"]


def test_get_daemon_by_worker_name(app_client: TestClient, headers_for) -> None:
    response = app_client.get("/admin/daemons/dummy", headers=headers_for(ADMIN))
    assert response.status_code == 200
    assert response.json()["daemon"]["worker_name"] == "dummy"


def test_get_daemon_unknown_returns_404(app_client: TestClient, headers_for) -> None:
    response = app_client.get("/admin/daemons/ghost", headers=headers_for(ADMIN))
    assert response.status_code == 404


def test_get_daemon_malformed_worker_name_returns_422(
    app_client: TestClient, headers_for
) -> None:
    response = app_client.get("/admin/daemons/Bad-Name", headers=headers_for(ADMIN))
    assert response.status_code == 422


def test_post_daemon_creates_and_can_login(app_client: TestClient, headers_for) -> None:
    response = app_client.post(
        "/admin/daemons",
        json={"worker_name": "worker2", "daemon_password": "worker2-password"},
        headers=headers_for(ADMIN),
    )
    assert response.status_code == 200

    headers = headers_for("daemon:worker2@localhost", password="worker2-password")
    response = app_client.post("/daemon/message-buffer/clear", headers=headers)
    assert response.status_code == 200


def test_post_daemon_duplicate_returns_409(app_client: TestClient, headers_for) -> None:
    response = app_client.post(
        "/admin/daemons",
        json={"worker_name": "dummy", "daemon_password": "irrelevant"},
        headers=headers_for(ADMIN),
    )
    assert response.status_code == 409


def test_delete_daemon_removes_account(
    app_client: TestClient, headers_for
) -> None:
    response = app_client.delete("/admin/daemons/dummy", headers=headers_for(ADMIN))
    assert response.status_code == 200
    # The account is gone: a follow-up admin read 404s.
    assert (
        app_client.get(
            "/admin/daemons/dummy", headers=headers_for(ADMIN)
        ).status_code
        == 404
    )


def test_delete_daemon_unknown_returns_404(app_client: TestClient, headers_for) -> None:
    response = app_client.delete("/admin/daemons/ghost", headers=headers_for(ADMIN))
    assert response.status_code == 404


# ─── Users ─────────────────────────────────────────────────────────


def test_get_users_lists_user_ids(app_client: TestClient, headers_for) -> None:
    response = app_client.get("/admin/users", headers=headers_for(ADMIN))
    assert response.status_code == 200
    assert sorted(response.json()["users"]) == ["alice", "bob"]


def test_get_user_by_id(app_client: TestClient, headers_for) -> None:
    response = app_client.get("/admin/users/alice", headers=headers_for(ADMIN))
    assert response.status_code == 200
    assert response.json()["user"]["user_id"] == "alice"


def test_get_user_unknown_returns_404(app_client: TestClient, headers_for) -> None:
    response = app_client.get("/admin/users/ghost", headers=headers_for(ADMIN))
    assert response.status_code == 404


def test_post_user_creates_and_can_login(app_client: TestClient, headers_for) -> None:
    response = app_client.post(
        "/admin/users",
        json={"user_id": "carol", "user_password": "carol-password"},
        headers=headers_for(ADMIN),
    )
    assert response.status_code == 200
    assert response.json()["user"]["user_id"] == "carol"

    headers = headers_for("user:carol@localhost", password="carol-password")
    response = app_client.get("/inbox", headers=headers)
    assert response.status_code == 200


def test_post_user_duplicate_returns_409(app_client: TestClient, headers_for) -> None:
    response = app_client.post(
        "/admin/users",
        json={"user_id": "alice", "user_password": "irrelevant"},
        headers=headers_for(ADMIN),
    )
    assert response.status_code == 409


def test_delete_user_removes_account_and_boxes(
    app_client: TestClient, headers_for
) -> None:
    response = app_client.delete("/admin/users/bob", headers=headers_for(ADMIN))
    assert response.status_code == 200
    # The account is gone: a follow-up admin read 404s.
    assert (
        app_client.get(
            "/admin/users/bob", headers=headers_for(ADMIN)
        ).status_code
        == 404
    )


def test_delete_user_unknown_returns_404(app_client: TestClient, headers_for) -> None:
    response = app_client.delete("/admin/users/ghost", headers=headers_for(ADMIN))
    assert response.status_code == 404


# ─── Swarms ────────────────────────────────────────────────────────


def test_post_swarm_creates(app_client: TestClient, headers_for) -> None:
    response = app_client.post(
        "/admin/swarms",
        json={"name": "ensemble", "description": "A second swarm", "keywords": []},
        headers=headers_for(ADMIN),
    )
    assert response.status_code == 200
    assert response.json()["swarm"]["name"] == "ensemble"

    response = app_client.get("/swarms/ensemble", headers=headers_for(ADMIN))
    assert response.status_code == 200


def test_post_swarm_duplicate_returns_409(app_client: TestClient, headers_for) -> None:
    response = app_client.post(
        "/admin/swarms",
        json={"name": SWARM, "description": "dupe", "keywords": []},
        headers=headers_for(ADMIN),
    )
    assert response.status_code == 409


def test_delete_swarm_removes(app_client: TestClient, headers_for) -> None:
    response = app_client.delete(f"/admin/swarms/{SWARM}", headers=headers_for(ADMIN))
    assert response.status_code == 200

    response = app_client.get(f"/swarms/{SWARM}", headers=headers_for(ADMIN))
    assert response.status_code == 404


def test_delete_swarm_unknown_returns_404(app_client: TestClient, headers_for) -> None:
    response = app_client.delete(
        "/admin/swarms/nonexistent", headers=headers_for(ADMIN)
    )
    assert response.status_code == 404
