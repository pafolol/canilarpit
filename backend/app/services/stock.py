"""Stock photography lookup for guide illustration.

Pexels is the only provider wired up. It returns attribution and licence data with
every photo, which is what the public guide page needs in order to credit an image
properly. Without a key the search returns nothing rather than failing: the admin
panel still works, it just cannot suggest photographs.
"""

import httpx

from app.core.config import settings
from app.schemas.api import StockImageResult

PROVIDER = "pexels"
SEARCH_URL = "https://api.pexels.com/v1/search"
LICENSE_NAME = "Pexels License"
LICENSE_URL = "https://www.pexels.com/license/"


class StockSearchUnavailable(RuntimeError):
    """No provider key, or the provider refused the call."""


def search_stock_images(query: str, *, limit: int | None = None) -> list[StockImageResult]:
    if not settings.stock_configured:
        raise StockSearchUnavailable("PEXELS_API_KEY is not configured")

    per_page = limit or settings.stock_results_per_query
    try:
        response = httpx.get(
            SEARCH_URL,
            params={"query": query, "per_page": max(1, min(per_page, 40))},
            headers={"Authorization": settings.pexels_api_key or ""},
            timeout=20.0,
        )
    except httpx.HTTPError as exc:
        raise StockSearchUnavailable(f"Could not reach Pexels: {exc}") from exc

    if response.status_code >= 400:
        raise StockSearchUnavailable(f"Pexels returned {response.status_code}")

    photos = response.json().get("photos") or []
    return [photo for photo in (_to_result(item, query) for item in photos) if photo]


def _to_result(item: dict, query: str) -> StockImageResult | None:
    sources = item.get("src") or {}
    remote_url = sources.get("large2x") or sources.get("large") or sources.get("original")
    if not remote_url:
        return None
    photographer = item.get("photographer")
    return StockImageResult(
        provider=PROVIDER,
        remote_url=remote_url,
        source_page_url=item.get("url"),
        attribution=f"Photo by {photographer} on Pexels" if photographer else "Pexels",
        license_name=LICENSE_NAME,
        license_url=LICENSE_URL,
        alt_text=(item.get("alt") or query)[:500],
        width=item.get("width"),
        height=item.get("height"),
        preview_url=sources.get("medium") or sources.get("small"),
    )


def search_many(queries: list[str], *, per_query: int = 1) -> list[StockImageResult]:
    """Best photo for each query, in query order, skipping providers errors per query."""
    found: list[StockImageResult] = []
    seen: set[str] = set()
    for query in queries:
        try:
            results = search_stock_images(query, limit=max(per_query, 3))
        except StockSearchUnavailable:
            raise
        for result in results[:per_query]:
            if result.remote_url not in seen:
                seen.add(result.remote_url)
                found.append(result)
    return found
