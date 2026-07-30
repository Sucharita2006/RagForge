from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health_ok() -> None:
    resp = client.get("/api/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_ready_returns_database_flag() -> None:
    resp = client.get("/api/ready")
    assert resp.status_code == 200
    body = resp.json()
    assert "status" in body
    assert isinstance(body["database"], bool)
