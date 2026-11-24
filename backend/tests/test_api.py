from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_liveness_endpoint() -> None:
    response = client.get("/health/live")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_models_endpoint_does_not_expose_credentials() -> None:
    response = client.get("/api/v1/models")
    assert response.status_code == 200
    payload = response.json()
    assert isinstance(payload["data"], list)
    assert "api_key" not in response.text.lower()
    assert "secret" not in response.text.lower()


def test_provider_status_only_exposes_configuration_state() -> None:
    response = client.get("/api/v1/providers")
    assert response.status_code == 200
    for provider in response.json()["data"]:
        assert set(provider) == {"id", "configured", "base_url"}
