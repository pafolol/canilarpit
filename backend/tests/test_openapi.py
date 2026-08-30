from fastapi.testclient import TestClient
from sqlalchemy.exc import OperationalError

from app.db.session import get_db
from app.main import app


def test_liveness_does_not_require_database() -> None:
    response = TestClient(app).get("/health/live")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_openapi_contains_frontend_routes() -> None:
    paths = app.openapi()["paths"]
    expected = {
        "/api/v1/config",
        "/api/v1/categories",
        "/api/v1/guides",
        "/api/v1/guides/{slug}",
        "/api/v1/topic-requests",
        "/api/v1/me",
        "/api/v1/me/history",
        "/api/v1/me/saved",
        "/api/v1/admin/guides",
        "/api/v1/admin/media",
        "/api/v1/admin/media/stock-search",
        "/api/v1/admin/research-jobs",
        "/api/v1/admin/ai/generate",
        "/api/v1/admin/ai/status",
    }
    assert expected.issubset(paths)
    assert "security" not in paths["/api/v1/topic-requests"]["post"]
    assert "security" not in paths["/api/v1/config"]["get"]
    assert paths["/api/v1/me"]["get"]["security"] == [{"HTTPBearer": []}]


def test_guide_cards_expose_the_verdict_layer() -> None:
    schemas = app.openapi()["components"]["schemas"]
    assert set(schemas["LarpCard"]["properties"]) == {
        "entry_type",
        "verdict",
        "exposure_seconds",
        "unfalsifiable",
        "flags",
        "dek",
    }
    assert "larp" in schemas["GuideListItem"]["properties"]
    assert "larp" in schemas["GuideDetail"]["properties"]


class UnreachableSession:
    """Stands in for a session whose server is not there."""

    def _fail(self, *args, **kwargs):
        raise OperationalError("SELECT 1", {}, Exception("connection refused"))

    execute = _fail
    scalar = _fail
    close = lambda self: None  # noqa: E731


def test_an_unreachable_database_is_a_readable_503() -> None:
    app.dependency_overrides[get_db] = lambda: UnreachableSession()
    try:
        response = TestClient(app).get("/api/v1/categories")
    finally:
        app.dependency_overrides.pop(get_db, None)

    assert response.status_code == 503
    assert "DATABASE_URL" in response.json()["detail"]
