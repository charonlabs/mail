import pytest
from fastapi.testclient import TestClient


@pytest.mark.usefixtures("patched_server")
def test_root_endpoint():
    from mail.server import app

    with TestClient(app) as client:
        r = client.get("/")
        assert r.status_code == 200
        data = r.json()
        assert data["name"] == "mail"
        assert data["status"] == "ok"


@pytest.mark.usefixtures("patched_server")
def test_status_without_auth():
    from mail.server import app

    with TestClient(app) as client:
        r = client.get("/status")
        assert r.status_code == 401


@pytest.mark.usefixtures("patched_server")
def test_status_with_auth():
    from mail.server import app

    with TestClient(app) as client:
        r = client.get("/status", headers={"Authorization": "Bearer test-key"})
        assert r.status_code == 200
        data = r.json()
        assert data["swarm"]["status"] == "ready"
        assert data["user_mail_ready"] is False
        

@pytest.mark.usefixtures("patched_server")
def test_message_flow_success():
    from mail.server import app

    with TestClient(app) as client:
        r = client.post(
            "/message",
            headers={"Authorization": "Bearer test-key"},
            json={"message": "Hello"},
        )
        assert r.status_code == 200
        data = r.json()
        assert data["response"] is not None
