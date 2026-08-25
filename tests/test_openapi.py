from fastapi.testclient import TestClient

from app.main import app


def test_liveness_does_not_require_database() -> None:
    response = TestClient(app).get("/health/live")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_openapi_contains_frontend_routes() -> None:
    paths = app.openapi()["paths"]
    expected = {
        "/api/v1/categories",
        "/api/v1/guides",
        "/api/v1/guides/{slug}",
        "/api/v1/topic-requests",
        "/api/v1/me",
        "/api/v1/me/history",
        "/api/v1/me/saved",
        "/api/v1/admin/guides",
        "/api/v1/admin/media",
        "/api/v1/admin/research-jobs",
    }
    assert expected.issubset(paths)
    assert "security" not in paths["/api/v1/topic-requests"]["post"]
    assert paths["/api/v1/me"]["get"]["security"] == [{"HTTPBearer": []}]
