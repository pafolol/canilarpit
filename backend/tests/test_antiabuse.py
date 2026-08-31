"""The obstacles in front of the only unauthenticated write on the site.

Each one is tested on its own, because they are meant to be independent: any
single measure here is beatable, and the point is that they do not share a
weakness.
"""

import time

import pytest
from fastapi import HTTPException

from app.core import antiabuse
from app.core.config import settings


class FakeRequest:
    """Enough of a Request for the fingerprint."""

    def __init__(self, host: str = "203.0.113.7", **headers: str) -> None:
        self.client = type("Client", (), {"host": host})()
        self.headers = {"user-agent": "Mozilla/5.0", "accept-language": "en-GB", **headers}


def test_the_fingerprint_is_stable_and_opaque() -> None:
    first = antiabuse.client_hash(FakeRequest())
    again = antiabuse.client_hash(FakeRequest())
    assert first == again, "the same client must count against the same bucket"
    assert len(first) == 64
    assert "203.0.113.7" not in first, "no raw address survives into the hash"


def test_a_different_browser_is_a_different_client() -> None:
    one = antiabuse.client_hash(FakeRequest())
    two = antiabuse.client_hash(FakeRequest(**{"user-agent": "something else"}))
    assert one != two


def test_the_forwarded_header_is_ignored_unless_the_deployment_says_otherwise(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Otherwise anybody mints a fresh identity per request by setting a header."""
    spoofed = FakeRequest(**{"x-forwarded-for": "198.51.100.1"})
    monkeypatch.setattr(settings, "trust_forwarded_for", False)
    assert antiabuse.client_hash(spoofed) == antiabuse.client_hash(FakeRequest())

    monkeypatch.setattr(settings, "trust_forwarded_for", True)
    assert antiabuse.client_hash(spoofed) != antiabuse.client_hash(FakeRequest())


def test_a_token_only_works_for_the_client_it_was_issued_to(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "submission_min_seconds", 0.0)
    token = antiabuse.issue_form_token("client-one")
    antiabuse.check_form_token(token.value, "client-one")

    with pytest.raises(HTTPException) as error:
        antiabuse.check_form_token(token.value, "client-two")
    assert error.value.status_code == 400


def test_a_forged_or_malformed_token_is_refused() -> None:
    for bad in ("", "nonsense", "v1.123.deadbeef", "v2.123.abc", "v1.notanumber.abc"):
        with pytest.raises(HTTPException):
            antiabuse.check_form_token(bad, "client")


def test_a_token_used_instantly_is_refused() -> None:
    """A person reads the form first. A script does not."""
    token = antiabuse.issue_form_token("client")
    with pytest.raises(HTTPException, match="faster than anybody reads"):
        antiabuse.check_form_token(token.value, "client")


def test_an_expired_token_is_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "submission_token_ttl_seconds", 1)
    monkeypatch.setattr(settings, "submission_min_seconds", 0.0)
    token = antiabuse.issue_form_token("client")
    time.sleep(1.2)
    with pytest.raises(HTTPException, match="expired"):
        antiabuse.check_form_token(token.value, "client")


def test_the_honeypot_says_nothing_useful() -> None:
    antiabuse.check_honeypot(None)
    antiabuse.check_honeypot("")
    with pytest.raises(HTTPException) as error:
        antiabuse.check_honeypot("http://spam.example")
    # A bot that learns why it failed adapts, so the message explains nothing.
    assert "honeypot" not in error.value.detail.lower()
    assert "website" not in error.value.detail.lower()


def test_notes_must_be_long_enough_to_be_worth_reading() -> None:
    with pytest.raises(HTTPException, match="at least"):
        antiabuse.check_notes("too short")


def test_repeated_text_is_not_a_description() -> None:
    with pytest.raises(HTTPException, match="repeated text"):
        antiabuse.check_notes("spam " * 40)
    with pytest.raises(HTTPException, match="repeated text"):
        antiabuse.check_notes("a" * 200)


def test_a_wall_of_links_is_refused() -> None:
    """Distinct links, so this is the link rule rather than the variety rule."""
    notes = (
        "Wonderful cheap replica watches shipped worldwide from our friendly shop "
        "https://one.example https://two.example https://three.example "
        "www.four.example https://five.example"
    )
    with pytest.raises(HTTPException, match="Too many links"):
        antiabuse.check_notes(notes)


def test_a_real_description_passes() -> None:
    antiabuse.check_notes(
        "Orienteering is a running sport with a map and a compass. People talk about "
        "control points, route choice and relocating when they get lost. The tell is "
        "not being able to fold a map while running."
    )
