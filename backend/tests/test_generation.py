"""Generation is tested against a stub provider: no network, no key, no cost."""

import json
from pathlib import Path

import pytest

from app.core.config import settings
from app.db.models import EntryType, GuideType, Verdict
from app.services import ai, images

CONTENT = Path(__file__).resolve().parent.parent / "content" / "guides"
CATEGORIES = ["anime", "drink", "film", "general"]


def valid_document_json() -> str:
    """A real guide, replayed as if the model had written it."""
    return CONTENT.joinpath("letterboxd.json").read_text(encoding="utf-8")


def replay(*responses: str) -> ai.CompletionFn:
    remaining = list(responses)
    seen: list[list[dict[str, str]]] = []

    def complete(messages: list[dict[str, str]]) -> ai.Completion:
        seen.append(messages)
        return ai.Completion(text=remaining.pop(0), input_tokens=1000, output_tokens=2000)

    complete.seen = seen  # type: ignore[attr-defined]
    return complete


def test_a_valid_answer_becomes_a_guide_document() -> None:
    result = ai.generate_guide_document(
        "Letterboxd",
        category_slugs=CATEGORIES,
        guide_type=GuideType.GENERAL,
        entry_type=EntryType.TASTE,
        complete=replay(valid_document_json()),
    )
    assert result.document.slug == "letterboxd"
    assert result.document.larp.verdict.value == "yes"
    assert result.attempts == 1


def test_a_fenced_answer_is_still_read() -> None:
    fenced = f"```json\n{valid_document_json()}\n```"
    result = ai.generate_guide_document(
        "Letterboxd", category_slugs=CATEGORIES, complete=replay(fenced)
    )
    assert result.document.title == "Letterboxd"


def test_an_invalid_answer_is_sent_back_with_its_errors() -> None:
    broken = json.loads(valid_document_json())
    broken["content"]["larp"]["exposure_seconds"] = 5
    broken["content"]["larp"]["unfalsifiable"] = False

    complete = replay(json.dumps(broken), valid_document_json())
    result = ai.generate_guide_document(
        "Letterboxd", category_slugs=CATEGORIES, complete=complete
    )

    assert result.attempts == 2
    assert result.input_tokens == 2000
    repair_prompt = complete.seen[-1][-1]["content"]  # type: ignore[attr-defined]
    assert "did not validate" in repair_prompt
    assert "exposure_seconds" in repair_prompt


def test_giving_up_raises_rather_than_publishing_rubbish() -> None:
    attempts = settings.ai_max_repair_attempts + 1
    with pytest.raises(ai.AiGenerationFailed):
        ai.generate_guide_document(
            "Letterboxd",
            category_slugs=CATEGORIES,
            complete=replay(*(["{}"] * attempts)),
        )


def test_the_contract_documents_every_template() -> None:
    """A type the model cannot read about is a type it will never choose."""
    for guide_type in GuideType:
        assert f'"{guide_type.value}"' in ai.CONTRACT or f"{guide_type.value} -" in ai.CONTRACT

    for field in ("proof_of_work", "red_lines", "where_it_dips", "day_to_day"):
        assert field in ai.CONTRACT, f"{field} is undocumented"


def test_the_prompt_names_the_available_categories() -> None:
    messages = ai.build_prompt(
        "Attack on Titan",
        category_slugs=CATEGORIES,
        guide_type=GuideType.ANIME,
        entry_type=None,
        instructions="Include the ending.",
    )
    user = messages[1]["content"]
    assert "Attack on Titan" in user
    assert 'guide_type "anime"' in user
    assert "anime, drink, film, general" in user
    assert "Include the ending." in user


def test_the_verdict_scale_encourages_three_of_its_four_answers() -> None:
    """The site exists to help, so only genuine harm gets a refusal."""
    prompt = ai.SYSTEM_PROMPT
    for verdict in Verdict:
        assert f'"{verdict.value}"' in prompt, f"{verdict.value} is not explained"
    assert "not_really" not in prompt and "not_really" not in ai.CONTRACT

    # The failure mode we are guarding against: filing "hacking" under dont.
    assert "Difficult is \"talk_only\"" in prompt
    assert "endangers somebody or defrauds them" in prompt


def test_the_brief_asks_for_pictures_through_the_article() -> None:
    contract = ai.CONTRACT
    assert "4 to 6 pictures" in contract
    for section in ("crib", "surface", "tells", "cost", "learn", "gallery"):
        assert section in contract
    assert 'role: "hero"' in contract


def test_the_image_plan_comes_from_the_document_and_names_a_provider() -> None:
    document = ai.generate_guide_document(
        "Natural wine",
        category_slugs=CATEGORIES,
        complete=replay(CONTENT.joinpath("natural-wine.json").read_text(encoding="utf-8")),
    ).document
    plan = ai.image_plan(document)

    assert plan
    assert plan[0].role == "hero", "the first picture is always the hero"
    assert {item.provider for item in plan} <= set(images.PROVIDERS) | {"auto"}
    assert len({(item.provider, item.query.lower()) for item in plan}) == len(plan)


def test_a_document_without_a_brief_still_gets_one() -> None:
    payload = json.loads(CONTENT.joinpath("naruto.json").read_text(encoding="utf-8"))
    payload["content"]["image_brief"] = []
    document = ai.GuideDocument.model_validate(payload)

    plan = ai.image_plan(document)
    assert plan, "an unbriefed guide falls back to its title"
    assert plan[0].role == "hero"


def test_the_prompt_lists_every_provider_and_what_it_is_for() -> None:
    guidance = ai.provider_guidance()
    for provider in images.PROVIDERS.values():
        assert provider.id in guidance
        assert provider.subjects in guidance
    assert "image_brief" in ai.CONTRACT


def test_cost_is_estimated_from_the_configured_rates() -> None:
    result = ai.GenerationResult(
        document=ai.GuideDocument.model_validate_json(valid_document_json()),
        input_tokens=1_000_000,
        output_tokens=1_000_000,
    )
    expected = int(
        round(
            (settings.openai_input_usd_per_million + settings.openai_output_usd_per_million)
            * 1_000_000
        )
    )
    assert result.estimated_cost_micros == expected


def test_dropping_a_dead_source_also_drops_its_citations() -> None:
    payload = json.loads(CONTENT.joinpath("naruto.json").read_text(encoding="utf-8"))
    assert payload["sources"], "the fixture must have a source to drop"
    ai._strip_citations(payload["content"], {source["key"] for source in payload["sources"]})

    citations = [
        citation
        for fact in payload["content"]["essential_facts"]
        for citation in fact["citations"]
    ]
    assert citations == []
