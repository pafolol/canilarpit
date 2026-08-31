import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import OperationalError

from app.db.session import get_db
from app.main import app, frontend_mounted


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
        "/api/v1/guides/{slug}/view",
        "/api/v1/learn",
        "/api/v1/presence",
        "/api/v1/topic-requests",
        "/api/v1/me",
        "/api/v1/me/history",
        "/api/v1/me/saved",
        "/api/v1/admin/guides",
        "/api/v1/admin/media",
        "/api/v1/admin/media/image-search",
        "/api/v1/admin/media/providers",
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
    # The count travels with the card, so a grid never needs a second round trip.
    assert "view_count" in schemas["GuideListItem"]["properties"]
    assert "view_count" in schemas["GuideDetail"]["properties"]


def test_counting_and_presence_are_open_to_anybody() -> None:
    """No sign-in: a reader cannot sign in, and the numbers are about readers."""
    paths = app.openapi()["paths"]
    assert "security" not in paths["/api/v1/guides/{slug}/view"]["post"]
    assert "security" not in paths["/api/v1/presence"]["post"]
    assert "security" not in paths["/api/v1/learn"]["get"]


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


def test_an_entry_page_still_loads_when_the_database_is_gone() -> None:
    """The app's own error state cannot show if the shell will not load.

    The sharing tags need a guide; the page does not. With no database the head
    falls back to the site's own title and the app renders and says what is wrong.
    """
    if not frontend_mounted:
        pytest.skip("no built frontend; run `npm run build`")
    app.dependency_overrides[get_db] = lambda: UnreachableSession()
    try:
        response = TestClient(app).get("/entry/naruto")
    finally:
        app.dependency_overrides.pop(get_db, None)

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert "<title>canilarpit" in response.text


def test_a_url_with_nothing_behind_it_is_a_real_404() -> None:
    """Rendering "not listed" under a 200 is a soft 404.

    The app draws its own not-listed page either way; what the status line
    changes is whether a crawler keeps the dead URL. The database is reachable
    here, so "no such guide" is a fact rather than a guess.
    """
    if not frontend_mounted:
        pytest.skip("no built frontend; run `npm run build`")
    client = TestClient(app)

    for path in ("/entry/no-such-guide-anywhere", "/category/no-such-category", "/invented"):
        assert client.get(path).status_code == 404, path

    # And the pages that do exist keep answering 200.
    for path in ("/", "/faq", "/privacy", "/submit"):
        assert client.get(path).status_code == 200, path
