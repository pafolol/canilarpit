"""Push the local catalog to a deployed Can I LARP It API.

The local database is the authoring copy: guides are written, generated and
illustrated here, and the deployed site should end up with the same content.
This walks the local catalog and replays it through the same admin API the
panel uses - categories, guide documents, image placements, publishing - so
nothing needs database access to the server.

    npm run db:upload -- --dry-run
    npm run db:upload -- --email you@example.com

Credentials, in the order it looks for them:

  --email / CANILARPIT_EMAIL, with the password in CANILARPIT_PASSWORD or typed
      at a prompt. The script signs in once and holds the session cookie for the
      whole run, so a long upload no longer races a credential's expiry.
  --dev-user / CANILARPIT_DEV_USER
      The development identity headers, which only a target running with
      DEV_AUTH_BYPASS=true accepts. For rehearsing against a second local API.

Importing and illustrating need the editor role; publishing needs admin. With
an editor account everything arrives as a draft and waits for an administrator.

What it deliberately does not send: users, saved guides, reading history, view
counts, presence, submissions, topic requests and the audit log. Those belong
to the deployment they happened on, and the server's counters are real readers
- replacing them with a development database would make the numbers a lie.
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from dataclasses import dataclass, field
from getpass import getpass
from typing import Any

import httpx
from sqlalchemy import select

from app.db.models import (
    Category,
    Guide,
    GuideMedia,
    GuideRevision,
    GuideStatus,
    MediaAsset,
)
from app.db.session import SessionLocal
from app.schemas.content import GuideDocument
from app.services.guides import document_hash, revision_document

DEFAULT_API_URL = "https://api.mcocvault.com/larp"


# --------------------------------------------------------------- local reading


@dataclass
class LocalMedia:
    """One picture, and where it sits in one guide."""

    provider: str
    kind: str
    remote_url: str | None
    storage_key: str | None
    source_page_url: str | None
    attribution: str | None
    license_name: str | None
    license_url: str | None
    alt_text: str
    width: int | None
    height: int | None
    metadata: dict[str, Any]
    approval_status: str
    role: str
    caption: str | None
    sort_order: int

    @property
    def key(self) -> tuple[str, str | None, str]:
        """What makes a placement the same placement at the other end."""
        return (self.provider, self.remote_url, self.role)

    def create_payload(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "provider": self.provider,
            "remote_url": self.remote_url,
            "storage_key": self.storage_key,
            "source_page_url": self.source_page_url,
            "attribution": self.attribution,
            "license_name": self.license_name,
            "license_url": self.license_url,
            "alt_text": self.alt_text,
            "width": self.width,
            "height": self.height,
            "metadata": self.metadata,
            "approval_status": self.approval_status,
        }


@dataclass
class LocalCategory:
    slug: str
    title: str
    description: str
    sort_order: int


@dataclass
class LocalGuide:
    slug: str
    title: str
    published: bool
    document: GuideDocument
    content_hash: str
    media: list[LocalMedia] = field(default_factory=list)


def read_local_catalog(slugs: list[str]) -> tuple[list[LocalCategory], list[LocalGuide]]:
    with SessionLocal() as db:
        categories = [
            LocalCategory(row.slug, row.title, row.description, row.sort_order)
            for row in db.scalars(
                select(Category)
                .where(Category.is_active.is_(True))
                .order_by(Category.sort_order, Category.title)
            ).all()
        ]

        query = select(Guide).order_by(Guide.slug)
        if slugs:
            query = query.where(Guide.slug.in_(slugs))

        guides: list[LocalGuide] = []
        for guide in db.scalars(query).all():
            # The published revision is what the site is actually serving; an
            # unpublished guide has only its newest draft to offer.
            revision = (
                db.get(GuideRevision, guide.current_revision_id)
                if guide.current_revision_id
                else db.scalar(
                    select(GuideRevision)
                    .where(GuideRevision.guide_id == guide.id)
                    .order_by(GuideRevision.revision_number.desc())
                    .limit(1)
                )
            )
            if revision is None:
                print(f"  ! {guide.slug} has no revision, skipped")
                continue

            document = revision_document(revision)
            media_rows = db.execute(
                select(GuideMedia, MediaAsset)
                .join(MediaAsset, MediaAsset.id == GuideMedia.media_asset_id)
                .where(GuideMedia.guide_revision_id == revision.id)
                .order_by(GuideMedia.sort_order, GuideMedia.id)
            ).all()
            guides.append(
                LocalGuide(
                    slug=guide.slug,
                    title=guide.title,
                    published=guide.status == GuideStatus.PUBLISHED,
                    document=document,
                    content_hash=document_hash(document),
                    media=[
                        LocalMedia(
                            provider=asset.provider,
                            kind=asset.kind.value,
                            remote_url=asset.remote_url,
                            storage_key=asset.storage_key,
                            source_page_url=asset.source_page_url,
                            attribution=asset.attribution,
                            license_name=asset.license_name,
                            license_url=asset.license_url,
                            alt_text=asset.alt_text,
                            width=asset.width,
                            height=asset.height,
                            metadata=asset.extra_metadata or {},
                            approval_status=asset.approval_status.value,
                            role=link.role,
                            caption=link.caption,
                            sort_order=link.sort_order,
                        )
                        for link, asset in media_rows
                    ],
                )
            )
    return categories, guides


# ------------------------------------------------------------------ the client


class UploadError(RuntimeError):
    pass


MAX_THROTTLE_RETRIES = 3
MAX_THROTTLE_WAIT_SECONDS = 90.0


def throttle_wait(response: httpx.Response) -> float:
    """How long the server asked us to wait, within reason."""
    try:
        asked = float(response.headers.get("retry-after", ""))
    except ValueError:
        asked = 30.0
    return min(max(asked, 1.0), MAX_THROTTLE_WAIT_SECONDS)


def detail(response: httpx.Response) -> str:
    """The API's own explanation, which is more useful than the status alone."""
    try:
        body = response.json()
    except ValueError:
        return response.text[:300]
    if isinstance(body, dict) and "detail" in body:
        return str(body["detail"])[:600]
    return str(body)[:300]


class Client:
    def __init__(self, http: httpx.Client, dry_run: bool) -> None:
        self.http = http
        self.dry_run = dry_run

    def request(self, method: str, path: str, **kwargs: Any) -> Any:
        # The session travels as a cookie, so a write has to echo the readable
        # half of the pair back as a header or the API refuses it.
        if method.upper() not in {"GET", "HEAD", "OPTIONS"}:
            csrf = self.http.cookies.get("canilarpit_csrf")
            if csrf:
                kwargs.setdefault("headers", {})
                kwargs["headers"] = {**kwargs["headers"], "X-CSRF-Token": csrf}

        for attempt in range(MAX_THROTTLE_RETRIES + 1):
            response = self.http.request(method, path, **kwargs)
            if response.status_code != 429 or attempt == MAX_THROTTLE_RETRIES:
                break
            # The admin surface has a per-minute ceiling, and replaying a whole
            # catalog is exactly the kind of legitimate burst that can reach it.
            # Wait the interval the server names rather than giving up half way
            # through — a partial upload is the worst outcome available.
            wait = throttle_wait(response)
            print(f"    rate limited; waiting {wait:.0f}s")
            time.sleep(wait)

        if response.status_code >= 400:
            raise UploadError(f"{method} {path} -> {response.status_code} {detail(response)}")
        if response.status_code == 204 or not response.content:
            return None
        return response.json()

    def get(self, path: str, **kwargs: Any) -> Any:
        return self.request("GET", path, **kwargs)

    def write(self, method: str, path: str, note: str, **kwargs: Any) -> Any:
        """A write that a dry run reports instead of performing."""
        if self.dry_run:
            print(f"    would {note}")
            return None
        return self.request(method, path, **kwargs)


# ------------------------------------------------------------------- the steps


def sync_categories(
    client: Client, categories: list[LocalCategory], failures: list[str]
) -> tuple[int, int]:
    """Create the categories the target is missing.

    The API derives a category's slug from the name it is given, so the local
    slug is what gets posted and the human title is applied afterwards - "job"
    has to stay "job" for the guides that reference it. A slug the target
    already has is left exactly as it is; its description is the deployment's
    own editorial choice.
    """
    remote = {row["slug"] for row in client.get("/api/v1/categories")}
    created = 0
    present = 0
    for category in categories:
        if category.slug in remote:
            present += 1
            continue
        print(f"  + {category.slug} ({category.title})")
        try:
            response = client.write(
                "POST",
                "/api/v1/admin/categories",
                f"create category {category.slug}",
                json={
                    "name": category.slug,
                    "description": category.description,
                    "sort_order": category.sort_order,
                },
            )
            created += 1
            if response and response["title"] != category.title:
                client.write(
                    "PATCH",
                    f"/api/v1/admin/categories/{response['id']}",
                    f"retitle {category.slug} to {category.title}",
                    json={"title": category.title},
                )
        except UploadError as exc:
            # Creating categories is an administrator's job. Carry on: the guides
            # that need this one will say so, and the rest still go up.
            failures.append(f"category {category.slug}: {exc}")
            print(f"    FAILED: {exc}")
    return created, present


def remote_guide_index(client: Client) -> dict[str, dict[str, Any]]:
    """Every guide the target has, by slug, with its revisions and imagery."""
    guides: dict[str, dict[str, Any]] = {}
    page = 1
    while True:
        body = client.get("/api/v1/admin/guides", params={"page": page, "page_size": 100})
        for item in body["items"]:
            guides[item["slug"]] = item
        if page >= (body["pagination"]["pages"] or 1):
            return guides
        page += 1


def media_keys(revision: dict[str, Any] | None) -> set[tuple[str, str | None, str]]:
    if not revision:
        return set()
    return {
        (item["provider"], item["url"], item["role"] or "gallery")
        for item in revision["media"]
    }


def remote_hash(revision: dict[str, Any]) -> str | None:
    """Hash the document the target returned, rather than trusting its stored one.

    A revision keeps the hash it was saved with, and a schema that has gained a
    field since then serializes to something else today. Re-hashing both sides
    with this checkout's code is the only comparison that means anything.
    """
    try:
        return document_hash(GuideDocument.model_validate(revision["document"]))
    except ValueError:
        return None


def is_current(local: LocalGuide, remote: dict[str, Any] | None) -> bool:
    """True when the target already serves this exact document and imagery."""
    if remote is None:
        return False
    if local.published:
        current = remote.get("current_revision")
        if remote["status"] != "published" or not current:
            return False
        if remote_hash(current) != local.content_hash:
            return False
        return {item.key for item in local.media} <= media_keys(current)
    draft = remote.get("draft_revision")
    return bool(draft and remote_hash(draft) == local.content_hash)


def link_media(
    client: Client, guide_id: str, revision: dict[str, Any], media: list[LocalMedia]
) -> tuple[int, int]:
    """Place this guide's pictures on the draft, skipping ones already there."""
    existing = media_keys(revision)
    placed = 0
    unavailable = 0
    for item in media:
        if item.key in existing:
            continue
        if not item.remote_url:
            # Uploaded and generated files live in the authoring deployment's
            # object storage, and this end has no way to hand the bytes over.
            print(f"    ! {item.provider} {item.role} image is a local upload, skipped")
            unavailable += 1
            continue
        asset = client.request("POST", "/api/v1/admin/media", json=item.create_payload())
        client.request(
            "POST",
            f"/api/v1/admin/guides/{guide_id}/draft/media",
            json={
                "media_asset_id": asset["id"],
                "role": item.role,
                "caption": item.caption,
                "sort_order": item.sort_order,
            },
        )
        existing.add(item.key)
        placed += 1
    return placed, unavailable


def upload_guide(
    client: Client, local: LocalGuide, remote: dict[str, Any] | None, publish: bool
) -> None:
    """Import the document, attach its images, then publish what was published.

    Import lands as a draft even for a published guide, because the images have
    to be placed on the draft before it goes live: publishing first would show
    readers a guide with no pictures until the second pass.
    """
    print(f"  {'~' if remote else '+'} {local.slug} ({local.title})")
    imported = client.write(
        "POST",
        "/api/v1/admin/guides/import",
        f"{'update' if remote else 'create'} {local.slug}"
        f" with {len(local.media)} image(s)"
        f"{', and publish it' if publish and local.published else ''}",
        params={"publish": False},
        json=local.document.model_dump(mode="json", exclude_none=True),
    )
    if imported is None:  # dry run
        return

    revision = imported.get("draft_revision") or imported.get("current_revision")
    if revision is None:
        raise UploadError(f"{local.slug}: the import returned no revision to work on")

    placed, unavailable = link_media(client, imported["id"], revision, local.media)
    if placed:
        print(f"    {placed} image(s) placed")
    if unavailable:
        print(f"    {unavailable} image(s) could not be sent")

    if publish and local.published:
        client.request(
            "POST",
            f"/api/v1/admin/guides/{imported['id']}/publish",
            json={"revision_id": revision["id"]},
        )
        print("    published")


# ------------------------------------------------------------------------ main


def build_http_client(args: argparse.Namespace) -> httpx.Client:
    headers = {"Accept": "application/json"}
    if args.dev_user and not args.email:
        headers["X-Dev-User"] = args.dev_user
        headers["X-Dev-Email"] = f"{args.dev_user}@example.invalid"
        headers["X-Dev-Display-Name"] = "Catalog upload"
    elif not args.email:
        raise SystemExit(
            "No credential. Pass --email with an editor account, or set "
            "CANILARPIT_EMAIL. Use --dev-user only against a local API."
        )

    client = httpx.Client(
        base_url=args.api_url.rstrip("/"),
        headers=headers,
        timeout=args.timeout,
        follow_redirects=True,
    )

    if args.email:
        password = os.environ.get("CANILARPIT_PASSWORD") or getpass(
            f"Password for {args.email}: "
        )
        response = client.post(
            "/api/v1/auth/login", json={"email": args.email, "password": password}
        )
        if response.status_code >= 400:
            client.close()
            raise SystemExit(f"Sign-in failed: {response.status_code} {detail(response)}")
        who = response.json()
        print(f"Signed in as {who.get('email')} ({who.get('role')}).")

    return client


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--api-url", default=os.environ.get("CANILARPIT_API_URL", DEFAULT_API_URL))
    parser.add_argument("--email", default=os.environ.get("CANILARPIT_EMAIL"))
    parser.add_argument("--dev-user", default=os.environ.get("CANILARPIT_DEV_USER"))
    parser.add_argument("--slug", action="append", default=[], help="Only these guides")
    parser.add_argument("--dry-run", action="store_true", help="Say what would be sent, send none")
    parser.add_argument("--skip-media", action="store_true", help="Documents only, no images")
    parser.add_argument("--no-publish", action="store_true", help="Leave everything as a draft")
    parser.add_argument("--force", action="store_true", help="Re-send guides already up to date")
    parser.add_argument("--timeout", type=float, default=60.0)
    return parser.parse_args()


def main() -> int:
    # Guide titles, photographers and character names are not limited to the
    # console's codepage, and a UnicodeEncodeError mid-upload is a miserable way
    # to lose a run.
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            reconfigure(encoding="utf-8", errors="replace")

    args = parse_args()
    print(f"Reading the local catalog for {args.api_url}")
    categories, guides = read_local_catalog(args.slug)
    print(f"  {len(categories)} categories, {len(guides)} guides")

    failures: list[str] = []
    with build_http_client(args) as http:
        client = Client(http, args.dry_run)
        try:
            config = client.get("/api/v1/config")
            account = client.get("/api/v1/me")
        except UploadError as exc:
            # The sign-in above already succeeded if we got here with --email,
            # so this is the target being unreachable rather than a credential.
            raise SystemExit(f"Could not sign in to {args.api_url}: {exc}") from exc
        print(
            f"Target is {config['app_env']}, signed in as "
            f"{account.get('email') or account['id']} ({account['role']})"
        )
        if account["role"] not in {"editor", "admin"}:
            raise SystemExit(
                f"That account is a {account['role']}. Importing needs the editor role, "
                "publishing needs admin; ask an administrator to promote it."
            )
        publish = not args.no_publish and account["role"] == "admin"
        if not args.no_publish and not publish:
            print("! Not an administrator: everything arrives as a draft.")
        if args.dry_run:
            print("Dry run: nothing will be written.")

        print("Categories:")
        created, present = sync_categories(client, categories, failures)
        print(f"  {created} created, {present} already there")

        remote = remote_guide_index(client)
        print("Guides:")
        sent = 0
        skipped = 0
        for local in guides:
            if not args.force and is_current(local, remote.get(local.slug)):
                skipped += 1
                continue
            if args.skip_media:
                local.media = []
            try:
                upload_guide(client, local, remote.get(local.slug), publish)
                sent += 1
            except UploadError as exc:
                failures.append(f"{local.slug}: {exc}")
                print(f"    FAILED: {exc}")

    print(f"\n{sent} guide(s) sent, {skipped} already up to date, {len(failures)} failed.")
    for failure in failures:
        print(f"  {failure}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
