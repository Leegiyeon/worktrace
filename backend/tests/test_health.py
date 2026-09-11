from fastapi.testclient import TestClient

from app.api import health
from app.main import app


def test_health_check_returns_ok() -> None:
    client = TestClient(app)
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_liveness_check_returns_ok() -> None:
    response = TestClient(app).get("/health/live")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"


class FakeConnection:
    def __enter__(self) -> "FakeConnection":
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def execute(self, query: str) -> None:
        assert query == "SELECT 1"


def test_readiness_check_returns_ready_when_database_is_available(monkeypatch) -> None:
    monkeypatch.setattr(health, "connect", lambda settings, row_factory: FakeConnection())

    response = TestClient(app).get("/health/ready")

    assert response.status_code == 200
    assert response.json()["status"] == "ready"


def test_readiness_check_returns_safe_503_when_database_is_unavailable(monkeypatch) -> None:
    def fail_connect(settings, row_factory):
        raise RuntimeError("postgres password and host must not leak")

    monkeypatch.setattr(health, "connect", fail_connect)

    response = TestClient(app).get("/health/ready")

    assert response.status_code == 503
    assert response.json() == {"detail": "database unavailable"}
    assert "password" not in response.text
