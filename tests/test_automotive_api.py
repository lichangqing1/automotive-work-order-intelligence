from fastapi.testclient import TestClient

from automotive.api import app, get_index


def test_health_and_search() -> None:
    get_index.cache_clear()
    client = TestClient(app)
    assert client.get("/health").json() == {"status": "ok"}
    response = client.post("/cases/search?top_k=3", json={
        "vehicle_model": "Model-X", "ota_version": "6.2.1",
        "description": "central display black after OTA", "error_code": "IVI_E104",
    })
    assert response.status_code == 200
    assert len(response.json()) == 3
