"""End-to-end checks against a real PostgreSQL database.

These skip themselves when no migrated database is reachable, so `pytest` stays
useful on a laptop with nothing running. To include them:

    python -m alembic upgrade head
    canilarpit seed
    python -m pytest

The suite writes: it creates an editor account, a guide draft, and a topic
request. Point DATABASE_URL at a scratch database, not production.
"""

import uuid
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, select, text
from sqlalchemy.exc import SQLAlchemyError

from app.core.config import settings
from app.db.models import Guide, GuideStatus, TopicRequest, User, UserRole
from app.db.session import SessionLocal
from app.main import app

EDITOR_ID = "test:editor"
# Everything this suite writes is prefixed so teardown can find and remove it.
GUIDE_PREFIX = "test-larp-"
TOPIC_PREFIX = "test topic "
DEV_HEADERS = {
    "X-Dev-Clerk-User-Id": EDITOR_ID,
    "X-Dev-Email": "editor@example.test",
    "X-Dev-Display-Name": "Test editor",
}


def database_ready() -> tuple[bool, str]:
    try:
        with SessionLocal() as db:
            db.execute(text("SELECT 1"))
            published = db.scalar(
                select(Guide.id).where(Guide.status == GuideStatus.PUBLISHED).limit(1)
            )
    except SQLAlchemyError as exc:
        return False, f"database unavailable: {type(exc).__name__}"
    if published is None:
        return False, "database has no published guides; run `canilarpit seed`"
    return True, ""


READY, SKIP_REASON = database_ready()
pytestmark = pytest.mark.skipif(not READY, reason=SKIP_REASON or "database not ready")


@pytest.fixture(scope="module")
def client() -> Iterator[TestClient]:
    # The dev bypass is what lets these tests authenticate without Clerk. It is
    # refused outright when APP_ENV is production, so this cannot leak.
    if settings.is_production:
        pytest.skip("refusing to run write tests against a production configuration")
    settings.dev_auth_bypass = True
    with SessionLocal() as db:
        user = db.scalar(select(User).where(User.clerk_user_id == EDITOR_ID))
        if user is None:
            user = User(clerk_user_id=EDITOR_ID, email="editor@example.test")
            db.add(user)
        user.role = UserRole.ADMIN
        user.is_active = True
        db.commit()

    yield TestClient(app)

    # Leave the catalog as we found it. A run that litters the editor's dashboard
    # with archived stubs is a run nobody will want to repeat.
    with SessionLocal() as db:
        db.execute(delete(Guide).where(Guide.slug.startswith(GUIDE_PREFIX)))
        db.execute(
            delete(TopicRequest).where(TopicRequest.normalized_topic.startswith(TOPIC_PREFIX))
        )
        db.execute(delete(User).where(User.clerk_user_id == EDITOR_ID))
        db.commit()


def test_readiness_reaches_postgres(client: TestClient) -> None:
    assert client.get("/health/ready").json() == {"status": "ready"}


def test_config_reports_the_available_sign_in_paths(client: TestClient) -> None:
    body = client.get("/api/v1/config").json()
    assert body["dev_auth_bypass"] is True
    assert "clerk_configured" in body


def test_categories_count_only_published_guides(client: TestClient) -> None:
    categories = client.get("/api/v1/categories").json()
    assert categories
    assert sum(item["published_guide_count"] for item in categories) > 0


def test_search_finds_a_seeded_guide_and_carries_its_verdict(client: TestClient) -> None:
    body = client.get("/api/v1/guides", params={"q": "letterboxd"}).json()
    assert body["pagination"]["total"] >= 1
    card = body["items"][0]
    assert card["slug"] == "letterboxd"
    assert card["larp"]["verdict"] == "yes"
    assert card["larp"]["unfalsifiable"] is True
    assert card["larp"]["dek"]


def test_search_for_nothing_returns_an_empty_page(client: TestClient) -> None:
    body = client.get("/api/v1/guides", params={"q": "zzzz nonexistent topic"}).json()
    assert body["items"] == []
    assert body["pagination"]["pages"] == 0


def test_verdict_and_entry_type_filters_intersect(client: TestClient) -> None:
    body = client.get(
        "/api/v1/guides", params={"verdict": ["dont"], "entry_type": ["role"]}
    ).json()
    assert body["items"]
    for card in body["items"]:
        assert card["larp"]["verdict"] == "dont"
        assert card["larp"]["entry_type"] == "role"
        # A DON'T entry never runs a clock.
        assert card["larp"]["exposure_seconds"] is None


def test_a_guide_page_carries_the_whole_entry(client: TestClient) -> None:
    body = client.get("/api/v1/guides/natural-wine").json()
    larp = body["content"]["larp"]
    assert larp["crib"] and larp["tells"] and larp["cost"]
    assert larp["learn"]["hours"] > 0
    assert body["category"]["slug"] == "drink"
    assert isinstance(body["media"], list)


def test_a_missing_guide_is_a_404(client: TestClient) -> None:
    assert client.get("/api/v1/guides/not-a-real-guide").status_code == 404


def test_requesting_a_missing_topic_records_demand(client: TestClient) -> None:
    topic = f"Test topic {uuid.uuid4().hex[:8]}"  # normalizes under TOPIC_PREFIX
    body = client.post("/api/v1/topic-requests", json={"topic": topic}).json()
    assert body["recorded"] is True
    assert body["request_count"] == 1

    again = client.post("/api/v1/topic-requests", json={"topic": f"  {topic.upper()}  "}).json()
    assert again["request_count"] == 2, "normalization should hit the same counter"


def test_requesting_an_existing_topic_points_at_the_guide(client: TestClient) -> None:
    body = client.post("/api/v1/topic-requests", json={"topic": "Letterboxd"}).json()
    assert body["recorded"] is False
    assert body["matching_guide"]["slug"] == "letterboxd"


def test_admin_routes_refuse_anonymous_callers(client: TestClient) -> None:
    assert client.get("/api/v1/admin/guides").status_code == 401


def test_an_editor_sees_the_catalog_and_the_ai_status(client: TestClient) -> None:
    me = client.get("/api/v1/me", headers=DEV_HEADERS).json()
    assert me["role"] == "admin"

    guides = client.get("/api/v1/admin/guides", headers=DEV_HEADERS).json()
    assert guides["pagination"]["total"] >= 1

    status = client.get("/api/v1/admin/ai/status", headers=DEV_HEADERS).json()
    assert status["text_provider"] == "openai"
    assert status["text_configured"] is settings.ai_configured


def test_generation_is_refused_without_a_key(client: TestClient) -> None:
    if settings.ai_configured:
        pytest.skip("a real key is configured; this asserts the unconfigured path")
    response = client.post(
        "/api/v1/admin/ai/generate", json={"topic": "Attack on Titan"}, headers=DEV_HEADERS
    )
    assert response.status_code == 503
    assert "OPENAI_API_KEY" in response.json()["detail"]


def test_an_editor_can_draft_and_publish_a_guide(client: TestClient) -> None:
    """The full editorial loop, on a throwaway slug."""
    slug = f"{GUIDE_PREFIX}{uuid.uuid4().hex[:8]}"
    document = {
        "schema_version": 1,
        "slug": slug,
        "title": "Test entry",
        "summary": "A throwaway guide created by the integration test suite.",
        "guide_type": "general",
        "category_slug": "general",
        "aliases": [],
        "content": {
            "kind": "general",
            "larp": {
                "entry_type": "taste",
                "verdict": "kinda",
                "exposure_seconds": 300,
                "unfalsifiable": False,
                "flags": ["TEST ONLY"],
                "dek": "An entry written by a test, and it shows.",
                "crib": [{"heading": "References", "lines": ["One line worth saying."]}],
                "surface": ["What passes on first contact."],
                "follow_up": ['"And then what?"'],
                "tells": ["You wrote this in a test."],
                "cost": ["None. It is a test."],
                "learn": {"hours": 1, "book": "None", "make": "Nothing"},
            },
            "overview": "A guide that exists only while the tests run.",
            "quick_brief": ["This entry is not real."],
            "essential_facts": [],
            "talking_points": [],
            "vocabulary": [],
            "common_mistakes": [],
            "questions": [],
            "extra_sections": [],
            "spoiler_warning": False,
            "key_people": [],
            "timeline": [],
        },
        "sources": [],
        "last_verified_at": None,
    }

    created = client.post("/api/v1/admin/guides", json=document, headers=DEV_HEADERS)
    assert created.status_code == 201, created.text
    guide_id = created.json()["id"]

    try:
        assert client.get(f"/api/v1/guides/{slug}").status_code == 404, "drafts stay private"

        validated = client.post(
            f"/api/v1/admin/guides/{guide_id}/validate", headers=DEV_HEADERS
        ).json()
        assert validated["valid"] is True
        assert len(validated["content_hash"]) == 64

        review = client.post(
            f"/api/v1/admin/guides/{guide_id}/submit-for-review", headers=DEV_HEADERS
        )
        assert review.status_code == 200

        published = client.post(
            f"/api/v1/admin/guides/{guide_id}/publish",
            json={"revision_id": None},
            headers=DEV_HEADERS,
        )
        assert published.status_code == 200
        assert published.json()["status"] == "published"

        public = client.get(f"/api/v1/guides/{slug}")
        assert public.status_code == 200
        assert public.json()["larp"]["exposure_seconds"] == 300

        found = client.get("/api/v1/guides", params={"q": "Test entry"}).json()
        assert any(item["slug"] == slug for item in found["items"])
    finally:
        client.post(f"/api/v1/admin/guides/{guide_id}/archive", headers=DEV_HEADERS)

    assert client.get(f"/api/v1/guides/{slug}").status_code == 404, "archiving unpublishes"
