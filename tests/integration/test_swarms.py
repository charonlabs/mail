# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Charon Labs (contribution PR)

from fastapi.testclient import TestClient

SWARM = "chorus"


# ─── Server root endpoints ─────────────────────────────────────────


def test_root_reports_protocol_info(app_client: TestClient) -> None:
    response = app_client.get("/")
    assert response.status_code == 200
    payload = response.json()
    assert payload["protocol_name"] == "mail"
    assert payload["protocol_version"] == "2.0"
    assert payload["uptime"] >= 0


def test_health_reports_ok(app_client: TestClient) -> None:
    response = app_client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


# ─── Swarm endpoints ───────────────────────────────────────────────
# NOTE: the swarms router currently performs no authentication; these
# tests pin that behavior. If the swarm directory is meant to require
# auth, that's a spec decision — change these alongside the router.


def test_get_swarms_lists_seeded_swarm_without_auth(
    app_client: TestClient,
) -> None:
    response = app_client.get("/swarms/")
    assert response.status_code == 200
    swarms = response.json()["swarms"]
    assert len(swarms) == 1
    assert swarms[0]["name"] == SWARM


def test_get_swarm_by_name(app_client: TestClient) -> None:
    response = app_client.get(f"/swarms/{SWARM}")
    assert response.status_code == 200
    assert response.json()["swarm"]["name"] == SWARM


def test_get_swarm_unknown_returns_404(app_client: TestClient) -> None:
    response = app_client.get("/swarms/nonexistent")
    assert response.status_code == 404


def test_get_swarm_health(app_client: TestClient) -> None:
    response = app_client.get(f"/swarms/{SWARM}/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_get_swarm_health_unknown_returns_404(app_client: TestClient) -> None:
    response = app_client.get("/swarms/nonexistent/health")
    assert response.status_code == 404
