"""Tests for the application health endpoint."""

from fastapi.testclient import TestClient

from salesagent.main import app


def test_health() -> None:
    """The health endpoint reports a successful application status."""
    response = TestClient(app).get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
