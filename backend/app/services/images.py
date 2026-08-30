"""Image sourcing.

A guide about Breaking Bad needs a picture of Walter White; a guide about
sourdough needs a picture of bread. Those come from different places, so this
module is a registry of providers rather than one search function, and the
model picks which one to ask.

| Provider  | Key | Good for                                        | Rights          |
|-----------|-----|-------------------------------------------------|-----------------|
| pexels    | yes | Generic subjects: objects, places, food, people | Free licence    |
| wikimedia | no  | Real people, places, objects, marques           | CC, varies      |
| tvmaze    | no  | Television shows, characters, episodes          | Editorial only  |
| anilist   | no  | Anime and manga, plus their characters          | Editorial only  |
| jikan     | no  | Anime and its characters, via MyAnimeList       | Editorial only  |

| fanart    | yes | Transparent logos, banners and clear art        | Editorial only  |

TMDB was here and is not any more: it charges for commercial use, and this site
intends to be one. Film imagery therefore comes from Commons - directors,
premieres, locations - rather than from posters, which are somebody's property
anyway. fanart.tv stays, and resolves its ids through TVmaze for television and
Wikidata for film, neither of which costs anything.

"Editorial only" means the rights stay with whoever owns the film, show or
photograph. We record the attribution and the page it came from, and the admin
panel says so before anyone approves it.
"""

import re
import time
from collections.abc import Callable
from dataclasses import dataclass
from functools import partial
from typing import Any

import httpx

from app.core.config import settings
from app.schemas.api import ImageCandidate

USER_AGENT = "canilarpit/0.1 (+https://canilarpit.com)"
TIMEOUT = 20.0

EDITORIAL_LICENCE = "Editorial use; rights held by the copyright owner"


class ImageSearchUnavailable(RuntimeError):
    """No key for this provider, or the provider refused the call."""


def _get(url: str, **kwargs: Any) -> Any:
    headers = {"User-Agent": USER_AGENT, **kwargs.pop("headers", {})}
    try:
        response = httpx.get(url, headers=headers, timeout=TIMEOUT, **kwargs)
    except httpx.HTTPError as exc:
        raise ImageSearchUnavailable(f"Could not reach {url.split('/')[2]}: {exc}") from exc
    if response.status_code >= 400:
        raise ImageSearchUnavailable(f"{url.split('/')[2]} returned {response.status_code}")
    return response.json()


def _clip(text: str | None, fallback: str, limit: int = 480) -> str:
    return (" ".join((text or fallback).split()))[:limit] or fallback[:limit]


STOPWORDS = frozenset(
    {"the", "and", "with", "from", "that", "this", "into", "over", "your", "their"}
)


def _terms(text: str) -> set[str]:
    return {
        word
        for word in re.findall(r"[a-z0-9]+", text.lower())
        if len(word) > 3 and word not in STOPWORDS
    }


def keep_relevant(
    query: str, candidates: list[ImageCandidate], *, threshold: float = 0.5
) -> list[ImageCandidate]:
    """Drop loose full-text matches.

    Commons will happily answer "techno club dancefloor" with a photograph of a
    Bukharan folk dance, because both mention dancing. Providers that search by
    title - TVmaze, AniList - do not need this; free-text ones do.
    """
    wanted = _terms(query)
    if not wanted:
        return candidates
    scored = []
    for candidate in candidates:
        haystack = _terms(f"{candidate.subject or ''} {candidate.alt_text}")
        score = len(wanted & haystack) / len(wanted)
        if score >= threshold:
            scored.append((score, candidate))
    # Strongest match first: the provider's own ordering is only full-text rank.
    scored.sort(key=lambda pair: pair[0], reverse=True)
    return [candidate for _, candidate in scored]


def _commons_field(meta: dict[str, Any], key: str) -> str | None:
    """Commons returns small HTML fragments in these fields."""
    value = (meta.get(key) or {}).get("value")
    if not value:
        return None
    return " ".join(re.sub(r"<[^>]+>", " ", str(value)).split()) or None


# ---------------------------------------------------------------- pexels


def search_pexels(query: str, limit: int) -> list[ImageCandidate]:
    if not settings.pexels_api_key:
        raise ImageSearchUnavailable("PEXELS_API_KEY is not configured")
    body = _get(
        "https://api.pexels.com/v1/search",
        params={"query": query, "per_page": max(1, min(limit, 40))},
        headers={"Authorization": settings.pexels_api_key},
    )
    found: list[ImageCandidate] = []
    for item in body.get("photos") or []:
        src = item.get("src") or {}
        url = src.get("large2x") or src.get("large") or src.get("original")
        if not url:
            continue
        photographer = item.get("photographer")
        found.append(
            ImageCandidate(
                provider="pexels",
                remote_url=url,
                preview_url=src.get("medium") or src.get("small"),
                source_page_url=item.get("url"),
                attribution=f"Photo by {photographer} on Pexels" if photographer else "Pexels",
                license_name="Pexels License",
                license_url="https://www.pexels.com/license/",
                alt_text=_clip(item.get("alt"), query),
                width=item.get("width"),
                height=item.get("height"),
                subject=query,
            )
        )
    return found


# ---------------------------------------------------------------- wikimedia


def search_wikimedia(query: str, limit: int) -> list[ImageCandidate]:
    """Commons search. No key, and the licence travels with every file."""
    body = _get(
        "https://commons.wikimedia.org/w/api.php",
        params={
            "action": "query",
            "format": "json",
            "generator": "search",
            "gsrsearch": f"{query} filetype:bitmap",
            "gsrnamespace": 6,
            "gsrlimit": max(1, min(limit, 30)),
            "prop": "imageinfo",
            "iiprop": "url|size|extmetadata",
            "iiurlwidth": 1200,
        },
    )
    pages = ((body.get("query") or {}).get("pages") or {}).values()
    found: list[ImageCandidate] = []
    for page in pages:
        info = (page.get("imageinfo") or [{}])[0]
        url = info.get("thumburl") or info.get("url")
        if not url:
            continue
        meta = info.get("extmetadata") or {}
        field = partial(_commons_field, meta)

        title = str(page.get("title", "")).removeprefix("File:").rsplit(".", 1)[0]
        found.append(
            ImageCandidate(
                provider="wikimedia",
                remote_url=url,
                preview_url=info.get("thumburl"),
                source_page_url=info.get("descriptionurl"),
                attribution=field("Artist") or "Wikimedia Commons",
                license_name=field("LicenseShortName") or "See Commons file page",
                license_url=field("LicenseUrl"),
                alt_text=_clip(field("ImageDescription") or title, query),
                width=info.get("thumbwidth") or info.get("width"),
                height=info.get("thumbheight") or info.get("height"),
                subject=title or query,
            )
        )
    return keep_relevant(query, found)


# ---------------------------------------------------------------- tvmaze


def search_tvmaze(query: str, limit: int) -> list[ImageCandidate]:
    """The show, then the characters in it. TVmaze allows hotlinking; we cache anyway."""
    shows = _get("https://api.tvmaze.com/search/shows", params={"q": query})
    found: list[ImageCandidate] = []
    if not shows:
        return found

    top = shows[0].get("show") or {}
    show_name = top.get("name") or query
    image = top.get("image") or {}
    if image.get("original"):
        found.append(
            ImageCandidate(
                provider="tvmaze",
                remote_url=image["original"],
                preview_url=image.get("medium"),
                source_page_url=top.get("url"),
                attribution=f"{show_name} via TVmaze",
                license_name=EDITORIAL_LICENCE,
                license_url="https://www.tvmaze.com/api",
                alt_text=_clip(None, f"{show_name} — promotional image"),
                width=None,
                height=None,
                subject=show_name,
                editorial_only=True,
            )
        )

    show_id = top.get("id")
    if show_id and len(found) < limit:
        cast = _get(f"https://api.tvmaze.com/shows/{show_id}/cast")
        for member in cast:
            if len(found) >= limit:
                break
            character = member.get("character") or {}
            person = member.get("person") or {}
            portrait = (character.get("image") or {}) or (person.get("image") or {})
            if not portrait.get("original"):
                continue
            character_name = character.get("name") or person.get("name") or show_name
            found.append(
                ImageCandidate(
                    provider="tvmaze",
                    remote_url=portrait["original"],
                    preview_url=portrait.get("medium"),
                    source_page_url=character.get("url") or top.get("url"),
                    attribution=f"{character_name}, {show_name}, via TVmaze",
                    license_name=EDITORIAL_LICENCE,
                    license_url="https://www.tvmaze.com/api",
                    alt_text=_clip(None, f"{character_name} in {show_name}"),
                    width=None,
                    height=None,
                    subject=character_name,
                    editorial_only=True,
                )
            )
    return found


# ---------------------------------------------------------------- anilist

ANILIST_QUERY = """
query ($search: String, $perPage: Int) {
  Page(perPage: $perPage) {
    media(search: $search, type: ANIME, sort: SEARCH_MATCH) {
      id
      siteUrl
      bannerImage
      title { romaji english }
      coverImage { extraLarge large medium }
      characters(perPage: 6, sort: ROLE) {
        nodes { name { full } image { large medium } siteUrl }
      }
    }
  }
}
"""


ANILIST_CHARACTER_QUERY = """
query ($search: String, $perPage: Int) {
  Page(perPage: $perPage) {
    characters(search: $search) {
      name { full }
      image { large medium }
      siteUrl
      media(perPage: 1, sort: POPULARITY_DESC) { nodes { title { romaji english } } }
    }
  }
}
"""


def _anilist(document: str, variables: dict[str, Any]) -> dict:
    try:
        response = httpx.post(
            "https://graphql.anilist.co",
            json={"query": document, "variables": variables},
            headers={"User-Agent": USER_AGENT, "Content-Type": "application/json"},
            timeout=TIMEOUT,
        )
    except httpx.HTTPError as exc:
        raise ImageSearchUnavailable(f"Could not reach AniList: {exc}") from exc
    if response.status_code >= 400:
        raise ImageSearchUnavailable(f"AniList returned {response.status_code}")
    return (response.json().get("data") or {}).get("Page") or {}


def search_anilist_characters(query: str, limit: int) -> list[ImageCandidate]:
    """Character names are not series titles, so they need their own index."""
    page = _anilist(ANILIST_CHARACTER_QUERY, {"search": query, "perPage": max(1, limit)})
    found: list[ImageCandidate] = []
    for node in page.get("characters") or []:
        image = (node.get("image") or {}).get("large")
        name = (node.get("name") or {}).get("full")
        if not image or not name:
            continue
        shows = ((node.get("media") or {}).get("nodes")) or [{}]
        titles = shows[0].get("title") or {}
        show = titles.get("english") or titles.get("romaji")
        found.append(
            ImageCandidate(
                provider="anilist",
                remote_url=image,
                preview_url=(node.get("image") or {}).get("medium"),
                source_page_url=node.get("siteUrl"),
                attribution=f"{name}{f', {show},' if show else ''} via AniList",
                license_name=EDITORIAL_LICENCE,
                license_url="https://anilist.co/terms",
                alt_text=_clip(None, f"{name}{f' in {show}' if show else ''}"),
                width=None,
                height=None,
                subject=name,
                editorial_only=True,
            )
        )
    return found


def search_anilist(query: str, limit: int) -> list[ImageCandidate]:
    """Anime covers and banners, plus the main characters."""
    page = _anilist(ANILIST_QUERY, {"search": query, "perPage": 3})
    media_list = page.get("media") or []
    if not media_list:
        # The query was probably a character, not a series.
        return search_anilist_characters(query, limit)
    found: list[ImageCandidate] = []
    for media in media_list:
        names = media.get("title") or {}
        title = names.get("english") or names.get("romaji") or query
        cover = media.get("coverImage") or {}
        art = ((media.get("bannerImage"), "banner"), (cover.get("extraLarge"), "cover"))
        for url, label in art:
            if url and len(found) < limit:
                found.append(
                    ImageCandidate(
                        provider="anilist",
                        remote_url=url,
                        preview_url=cover.get("medium"),
                        source_page_url=media.get("siteUrl"),
                        attribution=f"{title} via AniList",
                        license_name=EDITORIAL_LICENCE,
                        license_url="https://anilist.co/terms",
                        alt_text=_clip(None, f"{title} — {label} image"),
                        width=None,
                        height=None,
                        subject=title,
                        editorial_only=True,
                    )
                )
        for node in ((media.get("characters") or {}).get("nodes")) or []:
            if len(found) >= limit:
                break
            image = (node.get("image") or {}).get("large")
            name = (node.get("name") or {}).get("full")
            if not image or not name:
                continue
            found.append(
                ImageCandidate(
                    provider="anilist",
                    remote_url=image,
                    preview_url=(node.get("image") or {}).get("medium"),
                    source_page_url=node.get("siteUrl") or media.get("siteUrl"),
                    attribution=f"{name}, {title}, via AniList",
                    license_name=EDITORIAL_LICENCE,
                    license_url="https://anilist.co/terms",
                    alt_text=_clip(None, f"{name} in {title}"),
                    width=None,
                    height=None,
                    subject=name,
                    editorial_only=True,
                )
            )
    return found


# ---------------------------------------------------------------- jikan


def search_jikan(query: str, limit: int) -> list[ImageCandidate]:
    """MyAnimeList through Jikan. Rate limited hard, so the two calls are spaced."""
    found: list[ImageCandidate] = []
    anime = _get(
        "https://api.jikan.moe/v4/anime",
        params={"q": query, "limit": max(1, min(limit, 10)), "sfw": "true"},
    )
    for item in anime.get("data") or []:
        images = ((item.get("images") or {}).get("jpg")) or {}
        url = images.get("large_image_url") or images.get("image_url")
        title = item.get("title_english") or item.get("title") or query
        if not url:
            continue
        found.append(
            ImageCandidate(
                provider="jikan",
                remote_url=url,
                preview_url=images.get("image_url"),
                source_page_url=item.get("url"),
                attribution=f"{title} via MyAnimeList",
                license_name=EDITORIAL_LICENCE,
                license_url="https://myanimelist.net/about/terms_of_use",
                alt_text=_clip(None, f"{title} — promotional image"),
                width=None,
                height=None,
                subject=title,
                editorial_only=True,
            )
        )

    if len(found) < limit:
        time.sleep(1.0)  # Jikan allows roughly three requests a second; be well under.
        try:
            characters = _get(
                "https://api.jikan.moe/v4/characters",
                params={"q": query, "limit": max(1, min(limit, 10))},
            )
        except ImageSearchUnavailable:
            return found
        for item in characters.get("data") or []:
            if len(found) >= limit:
                break
            images = ((item.get("images") or {}).get("jpg")) or {}
            url = images.get("image_url")
            name = item.get("name")
            if not url or not name:
                continue
            found.append(
                ImageCandidate(
                    provider="jikan",
                    remote_url=url,
                    preview_url=url,
                    source_page_url=item.get("url"),
                    attribution=f"{name} via MyAnimeList",
                    license_name=EDITORIAL_LICENCE,
                    license_url="https://myanimelist.net/about/terms_of_use",
                    alt_text=_clip(None, f"{name} — character portrait"),
                    width=None,
                    height=None,
                    subject=name,
                    editorial_only=True,
                )
            )
    return found


# ---------------------------------------------------------------- fanart

FANART_ART_KEYS = (
    ("hdtvlogo", "logo"),
    ("hdmovielogo", "logo"),
    ("clearlogo", "logo"),
    ("showbackground", "background"),
    ("moviebackground", "background"),
    ("tvthumb", "thumbnail"),
    ("moviethumb", "thumbnail"),
    ("hdclearart", "clear art"),
)


def _tvdb_id(query: str) -> tuple[str | None, str]:
    """TVmaze knows a show's TheTVDB id, which is how fanart keys television."""
    shows = _get("https://api.tvmaze.com/search/shows", params={"q": query})
    if not shows:
        return None, query
    show = shows[0].get("show") or {}
    externals = show.get("externals") or {}
    tvdb = externals.get("thetvdb")
    return (str(tvdb) if tvdb else None), (show.get("name") or query)


def _imdb_id(query: str) -> tuple[str | None, str]:
    """Wikidata knows a film's IMDb id (P345), which is how fanart keys film."""
    found = _get(
        "https://www.wikidata.org/w/api.php",
        params={
            "action": "wbsearchentities",
            "search": query,
            "language": "en",
            "format": "json",
            "type": "item",
            "limit": 5,
        },
    )
    ids = [item["id"] for item in (found.get("search") or []) if item.get("id")]
    if not ids:
        return None, query

    entities = _get(
        "https://www.wikidata.org/w/api.php",
        params={
            "action": "wbgetentities",
            "ids": "|".join(ids),
            "props": "claims|labels",
            "languages": "en",
            "format": "json",
        },
    ).get("entities") or {}

    for entity_id in ids:
        entity = entities.get(entity_id) or {}
        claims = entity.get("claims") or {}
        # P31 instance-of Q11424 film, so a director with the same name is skipped.
        kinds = {
            (((claim.get("mainsnak") or {}).get("datavalue") or {}).get("value") or {}).get("id")
            for claim in claims.get("P31") or []
        }
        if "Q11424" not in kinds:
            continue
        for claim in claims.get("P345") or []:
            value = ((claim.get("mainsnak") or {}).get("datavalue") or {}).get("value")
            if value:
                label = ((entity.get("labels") or {}).get("en") or {}).get("value") or query
                return str(value), label
    return None, query


def search_fanart(query: str, limit: int) -> list[ImageCandidate]:
    """Logos and clear art. fanart is keyed by id, so the title is resolved first."""
    if not settings.fanart_api_key:
        raise ImageSearchUnavailable("FANART_API_KEY is not configured")

    tvdb, name = _tvdb_id(query)
    art: dict[str, Any] = {}
    if tvdb:
        try:
            art = _get(
                f"https://webservice.fanart.tv/v3/tv/{tvdb}",
                params={"api_key": settings.fanart_api_key},
            )
        except ImageSearchUnavailable:
            art = {}

    if not art:
        imdb, name = _imdb_id(query)
        if not imdb:
            return []
        try:
            art = _get(
                f"https://webservice.fanart.tv/v3/movies/{imdb}",
                params={"api_key": settings.fanart_api_key},
            )
        except ImageSearchUnavailable:
            return []

    # Round-robin the art types, so three logos do not crowd out the background
    # and the thumbnail. Depth in one type is rarely what a guide wants.
    buckets = [
        [item for item in (art.get(key) or []) if item.get("url")]
        for key, _ in FANART_ART_KEYS
    ]
    ordered: list[tuple[dict, str]] = []
    for depth in range(max((len(bucket) for bucket in buckets), default=0)):
        for bucket, (_, label) in zip(buckets, FANART_ART_KEYS, strict=True):
            if depth < len(bucket):
                ordered.append((bucket[depth], label))

    found: list[ImageCandidate] = []
    for item, label in ordered[:limit]:
        found.append(
            ImageCandidate(
                provider="fanart",
                remote_url=item["url"],
                preview_url=item["url"],
                source_page_url="https://fanart.tv/",
                attribution=f"{name} {label} via fanart.tv",
                license_name=EDITORIAL_LICENCE,
                license_url="https://fanart.tv/terms-of-service/",
                alt_text=_clip(None, f"{name} - {label}"),
                width=None,
                height=None,
                subject=name,
                editorial_only=True,
            )
        )
    return found


# ---------------------------------------------------------------- registry


@dataclass(frozen=True)
class Provider:
    id: str
    title: str
    subjects: str
    search: Callable[[str, int], list[ImageCandidate]]
    key_setting: str | None
    editorial_only: bool

    @property
    def configured(self) -> bool:
        if self.key_setting is None:
            return True
        return bool(getattr(settings, self.key_setting, None))


PROVIDERS: dict[str, Provider] = {
    provider.id: provider
    for provider in (
        Provider(
            "pexels",
            "Pexels",
            "Generic photography: objects, food, drink, places, sport, interiors, anonymous people",
            search_pexels,
            "pexels_api_key",
            False,
        ),
        Provider(
            "wikimedia",
            "Wikimedia Commons",
            "Real named people, buildings, marques, artefacts and places, freely licensed",
            search_wikimedia,
            None,
            False,
        ),
        Provider(
            "tvmaze",
            "TVmaze",
            "Television series, their characters and their episodes",
            search_tvmaze,
            None,
            True,
        ),
        Provider(
            "anilist",
            "AniList",
            "Anime and manga covers, banners and characters",
            search_anilist,
            None,
            True,
        ),
        Provider(
            "jikan",
            "MyAnimeList",
            "Anime and anime characters, as a second opinion to AniList",
            search_jikan,
            None,
            True,
        ),
        Provider(
            "fanart",
            "fanart.tv",
            "Transparent logos, banners and clear art for films and series",
            search_fanart,
            "fanart_api_key",
            True,
        ),
    )
}

# What "auto" means, by the kind of thing the guide is about. First configured
# provider in the list wins, so a missing key degrades instead of failing.
ROUTES: dict[str, list[str]] = {
    "anime": ["anilist", "jikan"],
    "film": ["wikimedia", "pexels"],
    "series": ["tvmaze", "fanart", "wikimedia"],
    "gaming": ["wikimedia", "pexels"],
    "books": ["wikimedia", "pexels"],
    "music": ["wikimedia", "pexels"],
    "job": ["pexels", "wikimedia"],
    "design": ["wikimedia", "pexels"],
    "style": ["pexels", "wikimedia"],
    "drink": ["pexels", "wikimedia"],
    "food": ["pexels", "wikimedia"],
    "sport": ["pexels", "wikimedia"],
    "tech": ["pexels", "wikimedia"],
}
DEFAULT_ROUTE = ["pexels", "wikimedia"]

# Providers substitute for each other only within a family. Asking a screen
# database for a film and settling for whatever Commons has under that title is
# how you illustrate "Jeanne Dielman" with an unrelated 1929 portrait.
FAMILIES: dict[str, list[str]] = {
    "generic": ["pexels", "wikimedia"],
    "screen": ["tvmaze", "fanart"],
    "anime": ["anilist", "jikan"],
}
FAMILY_OF = {name: family for family, names in FAMILIES.items() for name in names}


def available_providers() -> list[dict[str, Any]]:
    return [
        {
            "id": provider.id,
            "title": provider.title,
            "subjects": provider.subjects,
            "configured": provider.configured,
            "requires_key": provider.key_setting is not None,
            "editorial_only": provider.editorial_only,
        }
        for provider in PROVIDERS.values()
    ]


def route_for(guide_type: str | None, category_slug: str | None) -> list[str]:
    """Provider order for `auto`, best guess first, configured ones only."""
    order = ROUTES.get(guide_type or "") or ROUTES.get(category_slug or "") or DEFAULT_ROUTE
    configured = [name for name in order if PROVIDERS[name].configured]
    if configured:
        return configured
    return [name for name in ("wikimedia", "pexels") if PROVIDERS[name].configured]


def search_images(provider_id: str, query: str, limit: int = 12) -> list[ImageCandidate]:
    provider = PROVIDERS.get(provider_id)
    if provider is None:
        raise ImageSearchUnavailable(f"Unknown image provider: {provider_id}")
    if not provider.configured:
        raise ImageSearchUnavailable(
            f"{provider.title} is not configured"
            + (f" ({provider.key_setting.upper()})" if provider.key_setting else "")
        )
    return provider.search(query, limit)[:limit]


def search_with_fallback(
    query: str,
    *,
    provider_id: str = "auto",
    guide_type: str | None = None,
    category_slug: str | None = None,
    limit: int = 6,
) -> tuple[list[ImageCandidate], list[str]]:
    """Try the chosen provider, then the route, and report what went wrong on the way."""
    if provider_id in {"auto", ""}:
        order = route_for(guide_type, category_slug)
    else:
        siblings = FAMILIES.get(FAMILY_OF.get(provider_id, ""), [])
        order = [provider_id, *(name for name in siblings if name != provider_id)]
    problems: list[str] = []
    for name in order:
        try:
            results = search_images(name, query, limit)
        except ImageSearchUnavailable as exc:
            problems.append(str(exc))
            continue
        if results:
            return results, problems
        problems.append(f"{PROVIDERS[name].title} had nothing for {query!r}")
    return [], problems
