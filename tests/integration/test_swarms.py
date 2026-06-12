# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Charon Labs (contribution PR)

import pytest
from fastapi.testclient import TestClient

SWARM = "chorus"
USER = "user:alice@localhost"


# ─── Server root endpoints ─────────────────────────────────────────
# GET / and GET /health stay unauthenticated by design: they exist for
# pings and liveness probes.


def test_root_reports_protocol_info_without_auth(app_client: TestClient) -> None:
    response = app_client.get("/")
    assert response.status_code == 200
    payload = response.json()
    assert payload["protocol_name"] == "mail"
    assert payload["protocol_version"] == "2.0"
    assert payload["uptime"] >= 0


def test_health_reports_ok_without_auth(app_client: TestClient) -> None:
    response = app_client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


# ─── Swarm endpoints ───────────────────────────────────────────────
# The swarm directory requires an authenticated user-agent (any role):
# the detail endpoint exposes agent rosters. Federation discovery will
# be its own authenticated surface when remote delivery is specified.


@pytest.mark.parametrize(
    "path", ["/swarms/", f"/swarms/{SWARM}", f"/swarms/{SWARM}/health"]
)
def test_swarm_endpoints_reject_missing_token(
    app_client: TestClient, path: str
) -> None:
    response = app_client.get(path)
    assert response.status_code == 401


def test_get_swarms_lists_seeded_swarm(
    app_client: TestClient, headers_for
) -> None:
    response = app_client.get("/swarms/", headers=headers_for(USER))
    assert response.status_code == 200
    swarms = response.json()["swarms"]
    assert len(swarms) == 1
    assert swarms[0]["name"] == SWARM


def test_get_swarm_by_name(app_client: TestClient, headers_for) -> None:
    response = app_client.get(f"/swarms/{SWARM}", headers=headers_for(USER))
    assert response.status_code == 200
    assert response.json()["swarm"]["name"] == SWARM


def test_get_swarm_unknown_returns_404(
    app_client: TestClient, headers_for
) -> None:
    response = app_client.get("/swarms/nonexistent", headers=headers_for(USER))
    assert response.status_code == 404


def test_get_swarm_health(app_client: TestClient, headers_for) -> None:
    response = app_client.get(
        f"/swarms/{SWARM}/health", headers=headers_for(USER)
    )
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_get_swarm_health_unknown_returns_404(
    app_client: TestClient, headers_for
) -> None:
    response = app_client.get(
        "/swarms/nonexistent/health", headers=headers_for(USER)
    )
    assert response.status_code == 404
