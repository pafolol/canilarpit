"""End-to-end checks against a real PostgreSQL database.

These skip themselves when no migrated database is reachable, so `pytest` stays
useful on a laptop with nothing running. To include them:

    python -m alembic upgrade head
    canilarpit seed
    python -m pytest

The suite writes: it creates an editor account, a guide draft, and a topic
request. Point DATABASE_URL at a scratch database, not production.
"""

import json
import uuid
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, func, select, text
from sqlalchemy.exc import SQLAlchemyError

from app.core.config import settings
from app.db.models import (
    BlockedClient,
    Category,
    Guide,
    GuideMedia,
    GuideStatus,
    Submission,
    SubmissionStatus,
    TopicRequest,
    User,
    UserRole,
)
from app.db.session import SessionLocal
from app.main import app
from app.schemas.content import GuideDocument

EDITOR_ID = "test:editor"
# Everything this suite writes is prefixed so teardown can find and remove it.
GUIDE_PREFIX = "test-larp-"
TOPIC_PREFIX = "test topic "
CONTENT = Path(__file__).resolve().parent.parent / "content" / "guides"
SUBMISSION_PREFIX = "Test submission "
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


def discard_draft(guide_id: uuid.UUID) -> None:
    """Undo a draft this suite created on somebody's real guide."""
    from app.db.models import GuideRevision, MediaAsset, RevisionStatus

    with SessionLocal() as db:
        drafts = db.scalars(
            select(GuideRevision).where(
                GuideRevision.guide_id == guide_id,
                GuideRevision.status == RevisionStatus.DRAFT,
            )
        ).all()
        for draft in drafts:
            db.delete(draft)
        db.commit()

        orphans = db.scalars(
            select(MediaAsset.id).where(
                ~select(GuideMedia.id)
                .where(GuideMedia.media_asset_id == MediaAsset.id)
                .correlate(MediaAsset)
                .exists()
            )
        ).all()
        db.execute(delete(MediaAsset).where(MediaAsset.id.in_(orphans)))
        db.commit()


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
        db.execute(
            delete(Submission).where(Submission.topic.startswith(SUBMISSION_PREFIX))
        )
        db.execute(delete(BlockedClient))
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


def test_a_written_topic_leaves_the_backlog(client: TestClient) -> None:
    """The backlog is work to do, so a topic somebody has written is not on it."""
    unwritten = f"Test topic {uuid.uuid4().hex[:8]}"
    client.post("/api/v1/topic-requests", json={"topic": unwritten})

    # POST /topic-requests refuses to record a topic that already has a guide, so
    # a row for one is written straight to the table. This is the state a request
    # made before the guide existed leaves behind.
    written = f"Test topic {uuid.uuid4().hex[:8]}"
    with SessionLocal() as db:
        db.execute(delete(TopicRequest).where(TopicRequest.normalized_topic == "natural wine"))
        db.add(
            TopicRequest(topic=written, normalized_topic="natural wine", request_count=3)
        )
        db.commit()

    try:
        backlog = client.get(
            "/api/v1/admin/topic-requests", params={"page_size": 100}, headers=DEV_HEADERS
        ).json()
        topics = {item["topic"] for item in backlog["items"]}

        assert written not in topics, "natural-wine is published, so that is not work"
        # The positive half matters as much: a correlation bug in the filter once
        # hid the entire backlog, and an absence-only assertion sails past that.
        assert unwritten in topics, "an unwritten topic must stay on the backlog"

        everything = client.get(
            "/api/v1/admin/topic-requests",
            params={"include_written": True, "page_size": 100},
            headers=DEV_HEADERS,
        ).json()
        assert written in {item["topic"] for item in everything["items"]}
        assert everything["pagination"]["total"] > backlog["pagination"]["total"]
    finally:
        # This row is keyed on a real guide's topic, so the prefix teardown that
        # catches the rest of the suite's rows would leave it behind.
        with SessionLocal() as db:
            db.execute(
                delete(TopicRequest).where(TopicRequest.normalized_topic == "natural wine")
            )
            db.commit()


def test_an_editor_can_dismiss_a_request(client: TestClient) -> None:
    topic = f"Test topic {uuid.uuid4().hex[:8]}"
    client.post("/api/v1/topic-requests", json={"topic": topic})

    listed = client.get(
        "/api/v1/admin/topic-requests", params={"page_size": 100}, headers=DEV_HEADERS
    ).json()
    row = next(item for item in listed["items"] if item["topic"] == topic)

    path = f"/api/v1/admin/topic-requests/{row['id']}"
    assert client.delete(path, headers=DEV_HEADERS).status_code == 204
    # Idempotent: a second click is not an error.
    assert client.delete(path, headers=DEV_HEADERS).status_code == 204

    after = client.get(
        "/api/v1/admin/topic-requests", params={"page_size": 100}, headers=DEV_HEADERS
    ).json()
    assert not any(item["topic"] == topic for item in after["items"])


def test_regenerating_an_unknown_guide_is_a_404(client: TestClient) -> None:
    response = client.post(
        f"/api/v1/admin/guides/{uuid.uuid4()}/regenerate", json={}, headers=DEV_HEADERS
    )
    assert response.status_code == 404


def test_a_rewrite_lands_on_the_same_guide_even_if_the_model_renames_it() -> None:
    """The slug is pinned, so Regenerate can never fork a guide in two."""
    from app.db.models import GuideRevision, ResearchJobStatus
    from app.services import ai
    from app.services.generation import queue_generation_job, run_generation_job
    from app.services.guides import create_guide

    source = json.loads(
        (CONTENT / "letterboxd.json").read_text(encoding="utf-8")
    )
    slug = f"{GUIDE_PREFIX}{uuid.uuid4().hex[:8]}"

    with SessionLocal() as db:
        author = db.scalar(select(User).where(User.clerk_user_id == EDITOR_ID))
        document = GuideDocument.model_validate({**source, "slug": slug, "title": "Rewrite me"})
        guide = create_guide(db, document, author)
        db.commit()
        guide_id = guide.id

        # The model answers with a different slug, as it well might.
        renamed = json.dumps({**source, "slug": "somewhere-else", "title": "Somewhere else"})

        job = queue_generation_job(
            db,
            topic="Rewrite me",
            guide_type=document.guide_type,
            entry_type=document.content.larp.entry_type,
            category_slug=document.category_slug,
            instructions=None,
            attach_images=False,
            user=author,
            guide_id=guide_id,
        )
        job = run_generation_job(
            db,
            job.id,
            complete=lambda messages: ai.Completion(text=renamed),
        )

        assert job.status is ResearchJobStatus.REVIEW, job.error_message
        assert job.created_guide_id == guide_id, "the rewrite forked onto another guide"
        assert db.scalar(select(Guide).where(Guide.slug == "somewhere-else")) is None

        revisions = db.scalars(
            select(GuideRevision).where(GuideRevision.guide_id == guide_id)
        ).all()
        assert len(revisions) == 1, "an unpublished guide keeps one editable draft"
        assert revisions[0].content["title"] == "Somewhere else", "the rewrite did land"

        db.execute(delete(Guide).where(Guide.id == guide_id))
        db.commit()


def test_swapping_an_image_walks_down_the_same_search(client: TestClient) -> None:
    """No model call: the asset remembers the query and what it has already shown."""
    guides = client.get(
        "/api/v1/admin/guides", params={"page_size": 100}, headers=DEV_HEADERS
    ).json()["items"]
    illustrated = next(
        (
            guide
            for guide in guides
            if (guide["draft_revision"] or guide["current_revision"] or {}).get("media")
        ),
        None,
    )
    if illustrated is None:
        pytest.skip("no guide has images; run `canilarpit backfill-images`")

    guide_id = illustrated["id"]
    revision = illustrated["draft_revision"] or illustrated["current_revision"]
    placement = next(m for m in revision["media"] if m["link_id"])
    before = placement["url"]
    had_draft = illustrated["draft_revision"] is not None

    try:
        response = client.post(
            f"/api/v1/admin/guides/{guide_id}/draft/media/{placement['link_id']}/swap",
            headers=DEV_HEADERS,
        )
        if response.status_code == 404:
            pytest.skip(f"provider offered no alternative: {response.json()['detail']}")
        assert response.status_code == 200, response.text

        swapped = response.json()
        assert swapped["url"] != before, "a swap must actually change the image"
        assert swapped["role"] == placement["role"], "the slot is preserved"
        assert swapped["approval_status"] == placement["approval_status"]

        # Editing images never touches what is live.
        after = client.get(f"/api/v1/admin/guides/{guide_id}", headers=DEV_HEADERS).json()
        assert after["draft_revision"] is not None, "the edit landed on a draft"
        if illustrated["status"] == "published":
            assert after["current_revision_id"] == illustrated["current_revision_id"]
    finally:
        if not had_draft:
            discard_draft(uuid.UUID(guide_id))


def test_swapping_an_unknown_placement_is_a_404(client: TestClient) -> None:
    guides = client.get(
        "/api/v1/admin/guides", params={"page_size": 1}, headers=DEV_HEADERS
    ).json()["items"]
    response = client.post(
        f"/api/v1/admin/guides/{guides[0]['id']}/draft/media/{uuid.uuid4()}/swap",
        headers=DEV_HEADERS,
    )
    assert response.status_code == 404


SUBMISSION_NOTES = (
    "Orienteering is a running sport where you navigate between control points "
    "with a map and a compass. People argue about route choice and attack points, "
    "and the tell is not being able to fold a map while running."
)


def open_form(client: TestClient) -> str:
    return client.get("/api/v1/submissions/form").json()["token"]


def send(client: TestClient, token: str, **overrides):
    body = {"topic": "Orienteering", "notes": SUBMISSION_NOTES, "token": token}
    body.update(overrides)
    return client.post("/api/v1/submissions", json=body)


def submission_count() -> int:
    with SessionLocal() as db:
        return db.scalar(select(func.count()).select_from(Submission)) or 0


def test_a_submission_needs_a_token_from_the_form(client: TestClient) -> None:
    assert send(client, "v1.1.deadbeef").status_code == 400


def test_a_submission_sent_instantly_is_refused(client: TestClient) -> None:
    """A person reads the form. A script posts the moment it loads."""
    response = send(client, open_form(client))
    assert response.status_code == 400
    assert "faster" in response.json()["detail"]


def test_the_honeypot_is_silent(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "submission_min_seconds", 0.0)
    response = send(client, open_form(client), website="http://spam.example")
    assert response.status_code == 400
    assert "honeypot" not in response.json()["detail"].lower()


def test_a_thin_submission_is_refused(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "submission_min_seconds", 0.0)
    assert send(client, open_form(client), notes="dunno").status_code == 422


def test_a_topic_that_exists_points_at_the_guide_and_stores_nothing(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "submission_min_seconds", 0.0)
    before = submission_count()
    response = send(client, open_form(client), topic="Sourdough")

    assert response.status_code == 200, "nothing was created, so this is not a 201"
    body = response.json()
    assert body["received"] is False
    assert body["matching_guide"]["slug"] == "sourdough"
    assert submission_count() == before


def test_a_real_submission_is_stored_with_its_credit_and_no_raw_address(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "submission_min_seconds", 0.0)
    topic = f"{SUBMISSION_PREFIX}{uuid.uuid4().hex[:8]}"
    response = send(
        client, open_form(client), topic=topic, credit_name="A reader", category_slug="sport"
    )
    assert response.status_code == 201, response.text
    assert "A reader" in response.json()["message"]

    with SessionLocal() as db:
        row = db.scalar(select(Submission).where(Submission.topic == topic))
        assert row is not None
        assert row.status is SubmissionStatus.PENDING
        assert row.credit_name == "A reader"
        assert row.category_id is not None
        assert len(row.client_hash) == 64
        assert "127.0.0.1" not in row.client_hash, "no raw address is stored"


def test_the_same_client_cannot_send_the_same_topic_twice(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "submission_min_seconds", 0.0)
    topic = f"{SUBMISSION_PREFIX}{uuid.uuid4().hex[:8]}"
    assert send(client, open_form(client), topic=topic).status_code == 201
    assert send(client, open_form(client), topic=topic).status_code == 409


def test_the_pending_quota_bounds_the_queue(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The real limit is rows waiting, not requests made."""
    monkeypatch.setattr(settings, "submission_min_seconds", 0.0)
    monkeypatch.setattr(settings, "submission_max_pending", 1)
    # Earlier tests in this file share the fingerprint, so start from zero.
    with SessionLocal() as db:
        db.execute(delete(Submission).where(Submission.topic.startswith(SUBMISSION_PREFIX)))
        db.commit()

    first = f"{SUBMISSION_PREFIX}{uuid.uuid4().hex[:8]}"
    second = f"{SUBMISSION_PREFIX}{uuid.uuid4().hex[:8]}"
    assert send(client, open_form(client), topic=first).status_code == 201
    blocked = send(client, open_form(client), topic=second)
    assert blocked.status_code == 429
    assert "waiting" in blocked.json()["detail"]


def test_a_blocked_client_is_turned_away(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "submission_min_seconds", 0.0)
    topic = f"{SUBMISSION_PREFIX}{uuid.uuid4().hex[:8]}"
    assert send(client, open_form(client), topic=topic).status_code == 201

    with SessionLocal() as db:
        row = db.scalar(select(Submission).where(Submission.topic == topic))
        db.add(BlockedClient(client_hash=row.client_hash, reason="test"))
        db.commit()
    try:
        blocked = send(
            client, open_form(client), topic=f"{SUBMISSION_PREFIX}{uuid.uuid4().hex[:8]}"
        )
        assert blocked.status_code == 429
    finally:
        with SessionLocal() as db:
            db.execute(delete(BlockedClient))
            db.commit()


def test_submissions_are_editor_only(client: TestClient) -> None:
    assert client.get("/api/v1/admin/submissions").status_code == 401


def test_an_editor_sees_the_queue(client: TestClient) -> None:
    body = client.get("/api/v1/admin/submissions", headers=DEV_HEADERS).json()
    assert "items" in body
    assert "pagination" in body


def test_an_admin_can_promote_a_suggested_category(client: TestClient) -> None:
    name = f"test cat {uuid.uuid4().hex[:6]}"
    response = client.post("/api/v1/admin/categories", json={"name": name}, headers=DEV_HEADERS)
    assert response.status_code == 201, response.text
    created = response.json()
    assert created["slug"].startswith("test-cat-")
    with SessionLocal() as db:
        db.execute(delete(Category).where(Category.slug == created["slug"]))
        db.commit()


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
    # Wikimedia, TVmaze, AniList and Jikan need no key, so imagery always works.
    assert status["images_configured"] is True
    keyless = {p["id"] for p in status["image_providers"] if not p["requires_key"]}
    assert {"wikimedia", "tvmaze", "anilist", "jikan"} <= keyless


def test_the_seeded_guides_are_illustrated(client: TestClient) -> None:
    """The backfill ran, so a reader lands on pictures with their credits."""
    body = client.get("/api/v1/guides/prestige-tv").json()
    assert body["media"], "prestige-tv should carry television stills"
    hero = body["media"][0]
    assert hero["url"].startswith("http")
    assert hero["attribution"], "every image names where it came from"
    assert hero["license_name"]


def test_image_search_routes_a_character_to_a_screen_database(client: TestClient) -> None:
    found = client.get(
        "/api/v1/admin/media/image-search",
        params={"q": "Breaking Bad", "provider": "tvmaze", "limit": 4},
        headers=DEV_HEADERS,
    ).json()
    assert found["provider"] == "tvmaze"
    assert found["results"]
    assert all(item["editorial_only"] for item in found["results"])
    assert any("Walter White" in (item["subject"] or "") for item in found["results"])


def test_image_search_rejects_an_unknown_provider(client: TestClient) -> None:
    response = client.get(
        "/api/v1/admin/media/image-search",
        params={"q": "anything", "provider": "getty"},
        headers=DEV_HEADERS,
    )
    assert response.status_code == 422


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
                "follow_up": {
                    "question": '"And then what?"',
                    "why": "Because a test document has nowhere else to go.",
                    "counter": {
                        "move": "Admit it is a test and change the subject.",
                        "holds": "Until somebody reads the slug.",
                    },
                },
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
