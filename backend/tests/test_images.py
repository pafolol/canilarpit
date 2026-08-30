"""The image provider registry.

Routing and relevance are pure functions and get real tests. The providers
themselves talk to the internet, so they are exercised by hand and by
`canilarpit backfill-images`, not here.
"""

import pytest

from app.core.config import settings
from app.schemas.api import ImageCandidate
from app.services import images


def candidate(subject: str, alt: str = "", provider: str = "wikimedia") -> ImageCandidate:
    return ImageCandidate(
        provider=provider,
        remote_url=f"https://example.test/{subject.replace(' ', '-')}.jpg",
        alt_text=alt or subject,
        subject=subject,
    )


def test_every_provider_is_described_for_the_model() -> None:
    for provider in images.PROVIDERS.values():
        assert provider.subjects, f"{provider.id} has no description"
        assert provider.title
        assert provider.id in images.FAMILY_OF, f"{provider.id} belongs to no family"


def test_keyless_providers_are_always_available() -> None:
    keyless = {"wikimedia", "tvmaze", "anilist", "jikan"}
    for name in keyless:
        assert images.PROVIDERS[name].configured is True
    assert images.PROVIDERS["pexels"].configured is bool(settings.pexels_api_key)


def test_fanart_needs_tmdb_as_well_as_its_own_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "fanart_api_key", "fanart-key")
    monkeypatch.setattr(settings, "tmdb_api_key", None)
    assert images.PROVIDERS["fanart"].configured is False
    monkeypatch.setattr(settings, "tmdb_api_key", "tmdb-key")
    assert images.PROVIDERS["fanart"].configured is True


def test_routing_sends_anime_to_anime_databases() -> None:
    assert images.route_for("anime", "anime")[0] in {"anilist", "jikan"}


def test_routing_falls_through_unconfigured_providers(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "tmdb_api_key", None)
    # film routes to tmdb first, which has no key, so wikimedia answers instead.
    assert images.route_for(None, "film") == ["wikimedia"]
    monkeypatch.setattr(settings, "tmdb_api_key", "tmdb-key")
    assert images.route_for(None, "film") == ["tmdb", "wikimedia"]


def test_a_named_provider_only_falls_back_within_its_family() -> None:
    """A film is not in a stock library, so TMDB must never degrade to Pexels."""
    screen = images.FAMILIES["screen"]
    generic = images.FAMILIES["generic"]
    assert set(screen).isdisjoint(generic)
    assert images.FAMILY_OF["tmdb"] == "screen"
    assert images.FAMILY_OF["anilist"] == "anime"
    assert images.FAMILY_OF["pexels"] == "generic"


def test_unknown_provider_is_refused() -> None:
    with pytest.raises(images.ImageSearchUnavailable, match="Unknown image provider"):
        images.search_images("getty", "anything")


def test_relevance_drops_loose_full_text_matches() -> None:
    results = images.keep_relevant(
        "techno club dancefloor",
        [
            candidate("Bukharan dance performed by the Rina Nikova ballet"),
            candidate("Techno club dancefloor in Berlin"),
        ],
    )
    assert [item.subject for item in results] == ["Techno club dancefloor in Berlin"]


def test_relevance_ranks_the_closest_match_first() -> None:
    results = images.keep_relevant(
        "sourdough bread",
        [
            candidate("Focaccia", alt="focaccia bread with an open crumb"),
            candidate("Slices of sourdough bread"),
        ],
    )
    assert results[0].subject == "Slices of sourdough bread"


def test_relevance_leaves_short_queries_alone() -> None:
    """Nothing in "a cat" survives tokenising, so the provider's ranking stands."""
    given = [candidate("Anything at all")]
    assert images.keep_relevant("a cat", given) == given


def test_a_search_with_no_configured_provider_reports_why(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "pexels_api_key", None)
    with pytest.raises(images.ImageSearchUnavailable, match="PEXELS_API_KEY"):
        images.search_images("pexels", "sourdough")
