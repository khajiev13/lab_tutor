from fastapi.testclient import TestClient

from main import app

client = TestClient(app)


def test_read_root():
    response = client.get("/")
    assert response.status_code == 200
    assert response.json() == {"message": "Welcome to Lab Tutor"}


def test_health_check():
    response = client.get("/health")
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] in {"healthy", "degraded", "unhealthy"}
    assert isinstance(payload["checks"], list)

    checks_by_name = {c["name"]: c for c in payload["checks"]}
    assert checks_by_name["sql"]["status"] == "ok"
    assert checks_by_name["neo4j"]["status"] in {"ok", "skipped", "error"}
    assert checks_by_name["azure_blob"]["status"] in {"ok", "skipped", "error"}
