"""The verdict layer is the product, so its rules get their own tests."""

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.db.models import EntryType, Verdict
from app.schemas.content import GuideDocument, LarpProfile

CONTENT = Path(__file__).resolve().parent.parent / "content" / "guides"


def no_counter(profile: dict) -> dict:
    """A DON'T entry is valid only without a counter, and without lines to say."""
    profile["follow_up"] = {**profile["follow_up"], "counter": None}
    profile["phrases"] = []
    return profile


def base_profile(**overrides) -> dict:
    profile = {
        "entry_type": "taste",
        "verdict": "kinda",
        "exposure_seconds": 360,
        "unfalsifiable": False,
        "flags": ["HIGH VOCAB"],
        "dek": "Holds at the bar and fails at the table.",
        "crib": [{"heading": "References", "lines": ["One name worth saying."]}],
        "phrases": [{"line": "It's a bit reduced.", "when": "The first pour."}],
        "surface": ["What passes on first contact."],
        "follow_up": {
            "question": "\"Which vintage?\"",
            "why": "Vintage variation is the trapdoor.",
            "counter": {
                "move": "Hand the question back and ask what they made of it.",
                "holds": "The rest of the evening at the bar, not a seated tasting.",
            },
        },
        "tells": ["You call it natural wine. They say the producer."],
        "cost": ["Low. The scene forgives ignorance."],
        "learn": {"hours": 20, "book": "One book", "make": "One thing"},
    }
    profile.update(overrides)
    return profile


def test_every_seed_guide_carries_a_verdict() -> None:
    paths = list(CONTENT.glob("*.json"))
    assert paths
    for path in paths:
        document = GuideDocument.model_validate_json(path.read_text(encoding="utf-8"))
        assert document.content.larp is document.larp
        assert document.larp.verdict in set(Verdict)
        assert document.larp.entry_type in set(EntryType)


def test_a_dont_verdict_never_runs_a_clock() -> None:
    with pytest.raises(ValidationError, match="no clock"):
        LarpProfile.model_validate(base_profile(verdict="dont", exposure_seconds=300))

    profile = LarpProfile.model_validate(
        no_counter(base_profile(verdict="dont", exposure_seconds=None))
    )
    assert profile.exposure_seconds is None
    assert profile.unfalsifiable is False
    assert profile.follow_up.counter is None


def test_unfalsifiable_and_a_countdown_are_mutually_exclusive() -> None:
    with pytest.raises(ValidationError, match="cannot also carry an exposure clock"):
        LarpProfile.model_validate(base_profile(unfalsifiable=True, exposure_seconds=360))

    profile = LarpProfile.model_validate(base_profile(unfalsifiable=True, exposure_seconds=None))
    assert profile.unfalsifiable is True


def test_a_running_verdict_requires_a_clock() -> None:
    with pytest.raises(ValidationError, match="exposure_seconds is required"):
        LarpProfile.model_validate(base_profile(exposure_seconds=None))
    with pytest.raises(ValidationError, match="at least 30"):
        LarpProfile.model_validate(base_profile(exposure_seconds=5))


def test_flags_are_uppercased_and_deduplicated() -> None:
    profile = LarpProfile.model_validate(
        base_profile(flags=["high vocab", "HIGH VOCAB", "small scene", ""])
    )
    assert profile.flags == ["HIGH VOCAB", "SMALL SCENE"]


def test_crib_lines_cannot_be_blank() -> None:
    with pytest.raises(ValidationError, match="cannot be blank"):
        LarpProfile.model_validate(
            base_profile(crib=[{"heading": "References", "lines": ["   "]}])
        )


def test_a_guide_without_a_verdict_is_rejected() -> None:
    payload = json.loads((CONTENT / "letterboxd.json").read_text(encoding="utf-8"))
    del payload["content"]["larp"]
    with pytest.raises(ValidationError, match="larp"):
        GuideDocument.model_validate(payload)


def test_the_scale_has_no_refusal_left_in_it_but_dont() -> None:
    """Three of the four verdicts are a yes, and the seed content reflects that."""
    verdicts = [
        GuideDocument.model_validate_json(path.read_text(encoding="utf-8")).larp.verdict
        for path in CONTENT.glob("*.json")
    ]
    refusals = [v for v in verdicts if v is Verdict.DONT]
    assert len(refusals) <= 2, "DON'T is for harm, not for difficulty"
    assert Verdict.TALK_ONLY in verdicts, "the encouraging middle answer is in use"
    assert not hasattr(Verdict, "NOT_REALLY")


def test_a_talk_only_guide_still_carries_a_crib_sheet() -> None:
    """It is a yes, so the reader gets the thing they came for."""
    for path in CONTENT.glob("*.json"):
        document = GuideDocument.model_validate_json(path.read_text(encoding="utf-8"))
        if document.larp.verdict is Verdict.TALK_ONLY:
            assert document.larp.crib, f"{document.slug} has no crib sheet"


def test_a_dont_entry_offers_no_counter() -> None:
    """The answer to that question is not to have made the claim."""
    with pytest.raises(ValidationError, match="offers no counter"):
        LarpProfile.model_validate(base_profile(verdict="dont", exposure_seconds=None))


def test_every_larpable_guide_answers_its_own_question() -> None:
    for path in CONTENT.glob("*.json"):
        document = GuideDocument.model_validate_json(path.read_text(encoding="utf-8"))
        follow_up = document.larp.follow_up
        assert follow_up.question and follow_up.why
        if document.larp.verdict is Verdict.DONT:
            assert follow_up.counter is None
        else:
            assert follow_up.counter is not None, f"{document.slug} leaves the reader stuck"
            # An oversold counter gets somebody caught worse than none at all.
            assert follow_up.counter.holds, f"{document.slug} does not say how far it carries"


def test_a_dont_entry_hands_out_no_lines() -> None:
    profile = no_counter(base_profile(verdict="dont", exposure_seconds=None))
    profile["phrases"] = [{"line": "Anything at all.", "when": "Never."}]
    with pytest.raises(ValidationError, match="hands out no lines"):
        LarpProfile.model_validate(profile)


def test_every_larpable_guide_hands_over_something_to_say() -> None:
    """The crib is what to know; phrases are what comes out of your mouth."""
    for path in CONTENT.glob("*.json"):
        document = GuideDocument.model_validate_json(path.read_text(encoding="utf-8"))
        phrases = document.larp.phrases
        if document.larp.verdict is Verdict.DONT:
            assert not phrases
            continue
        assert len(phrases) >= 2, f"{document.slug} has nothing to say"
        for phrase in phrases:
            assert phrase.line and phrase.when
            # A phrase is spoken, so it stays short enough to actually say.
            assert len(phrase.line) <= 200
