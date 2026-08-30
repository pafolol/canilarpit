"""The verdict layer is the product, so its rules get their own tests."""

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.db.models import EntryType, Verdict
from app.schemas.content import GuideDocument, LarpProfile

CONTENT = Path(__file__).resolve().parent.parent / "content" / "guides"


def base_profile(**overrides) -> dict:
    profile = {
        "entry_type": "taste",
        "verdict": "kinda",
        "exposure_seconds": 360,
        "unfalsifiable": False,
        "flags": ["HIGH VOCAB"],
        "dek": "Holds at the bar and fails at the table.",
        "crib": [{"heading": "References", "lines": ["One name worth saying."]}],
        "surface": ["What passes on first contact."],
        "follow_up": ["\"Which vintage?\""],
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

    profile = LarpProfile.model_validate(base_profile(verdict="dont", exposure_seconds=None))
    assert profile.exposure_seconds is None
    assert profile.unfalsifiable is False


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
