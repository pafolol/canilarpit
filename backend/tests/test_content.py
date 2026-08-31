import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.schemas.api import ResearchJobCreate, SearchHistoryCreate, TopicRequestCreate
from app.schemas.content import GuideDocument, SourceDocument
from app.services.text import normalize_text, slugify


def test_all_seed_guides_match_schema() -> None:
    guide_paths = list(Path("content/guides").glob("*.json"))
    assert guide_paths
    for path in guide_paths:
        document = GuideDocument.model_validate_json(path.read_text(encoding="utf-8"))
        assert document.slug == path.stem


def test_unknown_citation_is_rejected() -> None:
    path = Path("content/guides/naruto.json")
    payload = GuideDocument.model_validate_json(path.read_text(encoding="utf-8")).model_dump(
        mode="json"
    )
    payload["content"]["essential_facts"][0]["citations"] = ["missing-source"]
    with pytest.raises(ValidationError, match="unknown citation keys"):
        GuideDocument.model_validate(payload)


def test_text_normalization() -> None:
    assert normalize_text("  Naruto: Shippuden! ") == "naruto shippuden"
    assert slugify("Luxury Watch Lifestyle") == "luxury-watch-lifestyle"


def test_non_string_slug_is_a_validation_error() -> None:
    payload = json.loads(Path("content/guides/naruto.json").read_text(encoding="utf-8"))
    payload["slug"] = 123
    with pytest.raises(ValidationError, match="slug must be a string"):
        GuideDocument.model_validate(payload)


@pytest.mark.parametrize(
    ("schema", "field"),
    [
        (TopicRequestCreate, "topic"),
        (ResearchJobCreate, "topic"),
        (SearchHistoryCreate, "query"),
    ],
)
def test_whitespace_write_inputs_are_rejected(schema: type, field: str) -> None:
    with pytest.raises(ValidationError):
        schema.model_validate({field: "   "})


def test_source_dates_require_timezone() -> None:
    with pytest.raises(ValidationError, match="datetime must include a timezone"):
        SourceDocument.model_validate(
            {
                "key": "source",
                "title": "Source",
                "url": "https://example.com",
                "verified_at": "2026-08-23T12:00:00",
            }
        )


def test_hard_spoilers_default_to_empty_and_survive_a_round_trip() -> None:
    """Every stored document predates this field, so it has to default cleanly."""
    payload = json.loads(Path("content/guides/sourdough.json").read_text(encoding="utf-8"))
    assert "hard_spoilers" not in payload["content"], "a craft guide has no plot"
    assert GuideDocument.model_validate(payload).content.hard_spoilers == []

    payload = json.loads(Path("content/guides/naruto.json").read_text(encoding="utf-8"))
    payload["content"]["hard_spoilers"][0]["reveal"] = "  Tobi   is    Obito.  "
    anime = GuideDocument.model_validate(payload)
    assert anime.content.hard_spoilers[0].reveal == "Tobi is Obito.", "whitespace collapses"
    assert anime.content.hard_spoilers[0].lands_because
    assert len(anime.content.hard_spoilers) == 2


def test_a_spoiler_needs_the_reason_it_lands() -> None:
    """A reveal with no reason is trivia, and trivia is what gets people caught."""
    payload = json.loads(Path("content/guides/naruto.json").read_text(encoding="utf-8"))
    payload["content"]["hard_spoilers"] = [{"reveal": "Tobi is Obito."}]
    with pytest.raises(ValidationError, match="lands_because"):
        GuideDocument.model_validate(payload)


def test_a_guide_cannot_carry_an_unbounded_pile_of_spoilers() -> None:
    """Three at most is the useful number; this is a card, not a plot summary."""
    payload = json.loads(Path("content/guides/naruto.json").read_text(encoding="utf-8"))
    payload["content"]["hard_spoilers"] = [
        {"reveal": f"Reveal {n}", "lands_because": "Because."} for n in range(7)
    ]
    with pytest.raises(ValidationError):
        GuideDocument.model_validate(payload)
