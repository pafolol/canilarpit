"""Serving the built app, and making a link to it worth sharing.

Slack, Discord, WhatsApp and every search crawler read the HTML that comes back
from the server and nothing else. They do not run JavaScript, so meta tags set
from React reach none of them: a shared entry link showed the same generic card
whatever it pointed at. The fix has to happen on the way out of FastAPI, which
means FastAPI has to be the thing that serves the page.

So: when `frontend/dist` exists, the API serves it, and `/entry/{slug}` gets the
guide's own title, description and hero image injected into the HTML before it
leaves. When `dist` is absent — the normal development case, where Vite serves
the frontend and proxies here — none of this is mounted and `npm run dev` is
untouched.

Everything here is registered after the API routers, so `/api/v1/*`, `/health`,
`/docs` and `/openapi.json` keep winning against the catch-all.
"""

import html
import logging
import re
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Depends, FastAPI, HTTPException, Response
from fastapi.responses import FileResponse, HTMLResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.models import Category, Guide, GuideStatus
from app.db.session import get_db
from app.services.guides import guide_detail, published_guide_by_slug

logger = logging.getLogger(__name__)

router = APIRouter(include_in_schema=False)

# The catch-all is deliberately greedy, so the paths the API owns are named here
# rather than left to route ordering alone. A miss under one of these is a 404,
# not a single-page app that renders "not listed" over a real routing mistake.
API_PREFIXES = ("api/", "health/", "health", "docs", "redoc", "openapi.json")

TITLE_PATTERN = re.compile(r"<title>.*?</title>", re.IGNORECASE | re.DOTALL)
DESCRIPTION_PATTERN = re.compile(
    r"""<meta\s+name=["']description["'][^>]*>""", re.IGNORECASE
)


def dist_dir() -> Path:
    """Where `npm run build` put the app, resolved against the repository root."""
    configured = Path(settings.frontend_dist)
    if configured.is_absolute():
        return configured
    # site.py → routes → api → app → backend → repository root
    return (Path(__file__).resolve().parents[4] / configured).resolve()


class IndexCache:
    """One read of index.html, held until the file changes underneath us.

    A build during a running server is a normal thing to do, so the mtime is
    checked on every request and the cost of being wrong is one stale page.
    """

    def __init__(self, path: Path) -> None:
        self.path = path
        self._mtime: float | None = None
        self._html = ""

    def read(self) -> str:
        mtime = self.path.stat().st_mtime
        if mtime != self._mtime:
            self._html = self.path.read_text(encoding="utf-8")
            self._mtime = mtime
        return self._html


index_cache: IndexCache | None = None


def attribute(value: str) -> str:
    """Escaped for an HTML attribute, and trimmed to what a preview card shows."""
    return html.escape(" ".join(value.split())[:300], quote=True)


def absolute(path: str) -> str:
    return f"{settings.site_origin}{path}"


def inject(document: str, *, title: str, description: str, url: str, image: str | None) -> str:
    """Replace the head's title and description, and add the sharing tags.

    The originals are replaced rather than appended to: two `<title>` elements
    means the first one wins, which would be the generic one.
    """
    tags = [
        f'<meta name="description" content="{attribute(description)}" />',
        '<meta property="og:type" content="article" />',
        '<meta property="og:site_name" content="canilarpit" />',
        f'<meta property="og:title" content="{attribute(title)}" />',
        f'<meta property="og:description" content="{attribute(description)}" />',
        f'<meta property="og:url" content="{attribute(url)}" />',
        f'<link rel="canonical" href="{attribute(url)}" />',
    ]
    if image:
        tags.append(f'<meta property="og:image" content="{attribute(image)}" />')
        tags.append('<meta name="twitter:card" content="summary_large_image" />')
        tags.append(f'<meta name="twitter:image" content="{attribute(image)}" />')
    else:
        tags.append('<meta name="twitter:card" content="summary" />')
    tags.append(f'<meta name="twitter:title" content="{attribute(title)}" />')
    tags.append(f'<meta name="twitter:description" content="{attribute(description)}" />')

    document = DESCRIPTION_PATTERN.sub("", document, count=1)
    document = TITLE_PATTERN.sub(
        f"<title>{html.escape(title)}</title>\n    " + "\n    ".join(tags),
        document,
        count=1,
    )
    return document


def entry_head(db: Session, slug: str) -> dict[str, str | None] | None:
    """The guide's own title, dek and approved hero, or None when there is no guide."""
    try:
        guide = published_guide_by_slug(db, slug)
        detail = guide_detail(db, guide)
    except (HTTPException, SQLAlchemyError):
        # A missing guide, or a database that is not there: the app still loads
        # and says so itself. A share card is not worth a 500.
        return None

    hero = next((m for m in detail.media if m.role == "hero" and m.url), None)
    hero = hero or next((m for m in detail.media if m.url), None)
    return {
        "title": f"{detail.title} — canilarpit",
        "description": detail.larp.dek or detail.summary,
        "url": absolute(f"/entry/{detail.slug}"),
        "image": hero.url if hero else None,
    }


@router.get("/robots.txt", response_class=PlainTextResponse)
def robots() -> str:
    """Crawlers are welcome on the catalog and nowhere else.

    The editorial panel is behind auth anyway; keeping it out of the index keeps
    it out of the way. The view counter thanks the disallow lines too: a crawler
    that never opens an entry never counts as a reader.
    """
    return "\n".join(
        [
            "User-agent: *",
            "Allow: /",
            "Disallow: /admin",
            "Disallow: /api/",
            f"Sitemap: {absolute('/sitemap.xml')}",
            "",
        ]
    )


def url_entry(path: str, lastmod: datetime | None, priority: str) -> str:
    parts = [f"    <loc>{html.escape(absolute(path))}</loc>"]
    if lastmod is not None:
        parts.append(f"    <lastmod>{lastmod.date().isoformat()}</lastmod>")
    parts.append(f"    <priority>{priority}</priority>")
    body = "\n".join(parts)
    return f"  <url>\n{body}\n  </url>"


@router.get("/sitemap.xml")
def sitemap(db: Session = Depends(get_db)) -> Response:
    """Every published entry, every category, and the pages worth landing on.

    Drafts and archived guides are absent by construction: the filter is the same
    published check the public API uses.
    """
    guides = db.execute(
        select(Guide.slug, Guide.updated_at)
        .where(Guide.status == GuideStatus.PUBLISHED)
        .order_by(Guide.slug)
    ).all()
    categories = db.scalars(
        select(Category.slug).where(Category.is_active.is_(True)).order_by(Category.slug)
    ).all()
    newest = max((row.updated_at for row in guides), default=None)

    urls = [
        url_entry("/", newest, "1.0"),
        url_entry("/just-learn-it", newest, "0.7"),
        url_entry("/submit", None, "0.5"),
        *[url_entry(f"/category/{slug}", None, "0.6") for slug in categories],
        *[url_entry(f"/entry/{slug}", updated_at, "0.8") for slug, updated_at in guides],
    ]
    body = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemap.org/schemas/sitemap/0.9">\n'
        + "\n".join(urls)
        + "\n</urlset>\n"
    ).replace("www.sitemap.org", "www.sitemaps.org")
    return Response(content=body, media_type="application/xml")


@router.get("/{path:path}", response_class=HTMLResponse)
def serve_app(path: str, db: Session = Depends(get_db)) -> Response:
    """The single-page app, with an entry's own sharing tags baked in when it is one."""
    if path.startswith(API_PREFIXES):
        raise HTTPException(status_code=404, detail="Not found")
    assert index_cache is not None  # only registered when dist exists

    # A real file in dist wins: favicon, manifest, anything the build emitted at
    # the root. Resolved and checked so no `..` walks out of the directory.
    if path:
        candidate = (index_cache.path.parent / path).resolve()
        if candidate.is_file() and candidate.is_relative_to(index_cache.path.parent):
            return FileResponse(candidate)

    document = index_cache.read()
    head: dict[str, str | None] | None = None
    if path.startswith("entry/"):
        head = entry_head(db, path[len("entry/") :].strip("/"))
    if head is None:
        head = {
            "title": "canilarpit — can you larp it, and for how long?",
            "description": (
                "A reference card for every scene, taste and role you might claim: "
                "what to say, what gives you away, and how long it holds."
            ),
            "url": absolute(f"/{path}" if path else "/"),
            "image": None,
        }

    return HTMLResponse(
        inject(
            document,
            title=head["title"] or "canilarpit",
            description=head["description"] or "",
            url=head["url"] or settings.site_origin,
            image=head["image"],
        )
    )


def mount_frontend(app: FastAPI) -> bool:
    """Attach the built app, if there is one. Returns whether anything was mounted."""
    global index_cache
    root = dist_dir()
    index = root / "index.html"
    if not index.is_file():
        logger.info("No built frontend at %s; serving the API only.", root)
        return False

    index_cache = IndexCache(index)
    assets = root / "assets"
    if assets.is_dir():
        app.mount("/assets", StaticFiles(directory=assets), name="assets")
    app.include_router(router)
    logger.info("Serving the built frontend from %s", root)
    return True
