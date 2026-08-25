import hashlib
import json
import math
import uuid
from datetime import UTC, datetime

from fastapi import HTTPException
from sqlalchemy import delete, func, select, update
from sqlalchemy.orm import Session

from app.db.models import (
    ApprovalStatus,
    Category,
    Guide,
    GuideAlias,
    GuideMedia,
    GuideRevision,
    GuideStatus,
    MediaAsset,
    RevisionStatus,
    Source,
    User,
)
from app.schemas.api import (
    AdminGuideResponse,
    AdminRevisionResponse,
    CategorySummary,
    GuideDetail,
    GuideListItem,
    MediaResponse,
    PaginationMeta,
    SourceResponse,
)
from app.schemas.content import GuideDocument
from app.services.storage import public_media_url
from app.services.text import normalize_text


def document_payload(document: GuideDocument) -> dict:
    return document.model_dump(mode="json", exclude_none=True)


def document_hash(document: GuideDocument) -> str:
    serialized = json.dumps(document_payload(document), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def pagination(page: int, page_size: int, total: int) -> PaginationMeta:
    return PaginationMeta(
        page=page,
        page_size=page_size,
        total=total,
        pages=math.ceil(total / page_size) if total else 0,
    )


def get_category_by_slug(db: Session, slug: str) -> Category:
    category = db.scalar(
        select(Category).where(Category.slug == slug, Category.is_active.is_(True))
    )
    if category is None:
        raise HTTPException(status_code=422, detail=f"Unknown category: {slug}")
    return category


def lock_guide(db: Session, guide: Guide) -> Guide:
    locked_guide = db.scalar(
        select(Guide)
        .where(Guide.id == guide.id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if locked_guide is None:
        raise HTTPException(status_code=404, detail="Guide not found")
    return locked_guide


def category_summary(category: Category) -> CategorySummary:
    return CategorySummary(id=category.id, slug=category.slug, title=category.title)


def get_guide_category(db: Session, guide: Guide) -> Category:
    category = db.get(Category, guide.category_id)
    if category is None:
        raise HTTPException(status_code=500, detail="Guide category is missing")
    return category


def guide_list_item(db: Session, guide: Guide, category: Category | None = None) -> GuideListItem:
    category = category or get_guide_category(db, guide)
    return GuideListItem(
        id=guide.id,
        slug=guide.slug,
        title=guide.title,
        summary=guide.summary,
        guide_type=guide.guide_type,
        category=category_summary(category),
        published_at=guide.published_at,
    )


def revision_document(revision: GuideRevision) -> GuideDocument:
    return GuideDocument.model_validate(revision.content)


def revision_response(db: Session, revision: GuideRevision | None) -> AdminRevisionResponse | None:
    if revision is None:
        return None
    media_rows = db.execute(
        select(GuideMedia, MediaAsset)
        .join(MediaAsset, MediaAsset.id == GuideMedia.media_asset_id)
        .where(GuideMedia.guide_revision_id == revision.id)
        .order_by(GuideMedia.sort_order, GuideMedia.id)
    ).all()
    return AdminRevisionResponse(
        id=revision.id,
        revision_number=revision.revision_number,
        status=revision.status,
        content_hash=revision.content_hash,
        document=revision_document(revision),
        media=[media_response(asset, link) for link, asset in media_rows],
        created_at=revision.created_at,
        updated_at=revision.updated_at,
        published_at=revision.published_at,
    )


def admin_guide_response(db: Session, guide: Guide) -> AdminGuideResponse:
    current_revision = (
        db.get(GuideRevision, guide.current_revision_id) if guide.current_revision_id else None
    )
    draft_revision = db.scalar(
        select(GuideRevision)
        .where(
            GuideRevision.guide_id == guide.id,
            GuideRevision.status.in_([RevisionStatus.DRAFT, RevisionStatus.IN_REVIEW]),
        )
        .order_by(GuideRevision.revision_number.desc())
        .limit(1)
    )
    return AdminGuideResponse(
        id=guide.id,
        slug=guide.slug,
        title=guide.title,
        summary=guide.summary,
        guide_type=guide.guide_type,
        status=guide.status,
        category=category_summary(get_guide_category(db, guide)),
        current_revision_id=guide.current_revision_id,
        current_revision=revision_response(db, current_revision),
        draft_revision=revision_response(db, draft_revision),
        published_at=guide.published_at,
        created_at=guide.created_at,
        updated_at=guide.updated_at,
    )


def replace_revision_sources(db: Session, revision: GuideRevision, document: GuideDocument) -> None:
    db.execute(delete(Source).where(Source.guide_revision_id == revision.id))
    for source in document.sources:
        db.add(
            Source(
                guide_revision_id=revision.id,
                source_key=source.key,
                title=source.title,
                url=str(source.url),
                publisher=source.publisher,
                excerpt=source.excerpt,
                published_at=source.published_at,
                verified_at=source.verified_at,
            )
        )


def replace_aliases(db: Session, guide: Guide, document: GuideDocument) -> None:
    db.execute(delete(GuideAlias).where(GuideAlias.guide_id == guide.id))
    for alias in document.aliases:
        db.add(GuideAlias(guide_id=guide.id, alias=alias, normalized_alias=normalize_text(alias)))


def create_guide(db: Session, document: GuideDocument, author: User) -> Guide:
    if db.scalar(select(Guide.id).where(Guide.slug == document.slug)):
        raise HTTPException(status_code=409, detail="A guide with this slug already exists")
    category = get_category_by_slug(db, document.category_slug)
    guide = Guide(
        slug=document.slug,
        title=document.title,
        summary=document.summary,
        guide_type=document.guide_type,
        category_id=category.id,
    )
    db.add(guide)
    db.flush()
    revision = GuideRevision(
        guide_id=guide.id,
        revision_number=1,
        schema_version=document.schema_version,
        content=document_payload(document),
        content_hash=document_hash(document),
        author_user_id=author.id,
    )
    db.add(revision)
    db.flush()
    replace_revision_sources(db, revision, document)
    replace_aliases(db, guide, document)
    db.flush()
    return guide


def save_draft(db: Session, guide: Guide, document: GuideDocument, author: User) -> GuideRevision:
    if document.slug != guide.slug:
        raise HTTPException(status_code=422, detail="A guide slug cannot be changed")
    guide = lock_guide(db, guide)
    get_category_by_slug(db, document.category_slug)
    draft = db.scalar(
        select(GuideRevision)
        .where(
            GuideRevision.guide_id == guide.id,
            GuideRevision.status.in_([RevisionStatus.DRAFT, RevisionStatus.IN_REVIEW]),
        )
        .order_by(GuideRevision.revision_number.desc())
        .limit(1)
    )
    if draft is None:
        next_number = db.scalar(
            select(func.coalesce(func.max(GuideRevision.revision_number), 0) + 1).where(
                GuideRevision.guide_id == guide.id
            )
        )
        draft = GuideRevision(
            guide_id=guide.id,
            revision_number=next_number,
            schema_version=document.schema_version,
            content=document_payload(document),
            content_hash=document_hash(document),
            author_user_id=author.id,
        )
        db.add(draft)
        db.flush()

        if guide.current_revision_id:
            current_media = db.scalars(
                select(GuideMedia).where(GuideMedia.guide_revision_id == guide.current_revision_id)
            ).all()
            for item in current_media:
                db.add(
                    GuideMedia(
                        guide_revision_id=draft.id,
                        media_asset_id=item.media_asset_id,
                        role=item.role,
                        caption=item.caption,
                        sort_order=item.sort_order,
                    )
                )
    else:
        draft.schema_version = document.schema_version
        draft.content = document_payload(document)
        draft.content_hash = document_hash(document)
        draft.author_user_id = author.id
        draft.status = RevisionStatus.DRAFT

    replace_revision_sources(db, draft, document)
    if guide.current_revision_id is None:
        guide.title = document.title
        guide.summary = document.summary
        guide.guide_type = document.guide_type
        guide.category_id = get_category_by_slug(db, document.category_slug).id
        replace_aliases(db, guide, document)
        guide.status = GuideStatus.DRAFT
    guide.updated_at = datetime.now(UTC)
    db.flush()
    return draft


def submit_for_review(db: Session, guide: Guide) -> GuideRevision:
    guide = lock_guide(db, guide)
    revision = db.scalar(
        select(GuideRevision)
        .where(GuideRevision.guide_id == guide.id, GuideRevision.status == RevisionStatus.DRAFT)
        .order_by(GuideRevision.revision_number.desc())
        .limit(1)
    )
    if revision is None:
        raise HTTPException(status_code=409, detail="This guide has no draft revision")
    revision.status = RevisionStatus.IN_REVIEW
    guide.updated_at = datetime.now(UTC)
    if guide.current_revision_id is None:
        guide.status = GuideStatus.IN_REVIEW
    db.flush()
    return revision


def publish_revision(
    db: Session, guide: Guide, revision_id: uuid.UUID | None = None
) -> GuideRevision:
    guide = lock_guide(db, guide)
    query = select(GuideRevision).where(GuideRevision.guide_id == guide.id)
    if revision_id:
        query = query.where(GuideRevision.id == revision_id)
    else:
        query = query.where(
            GuideRevision.status.in_([RevisionStatus.DRAFT, RevisionStatus.IN_REVIEW])
        ).order_by(GuideRevision.revision_number.desc())
    revision = db.scalar(query.with_for_update().limit(1))
    if revision is None:
        raise HTTPException(status_code=404, detail="Publishable revision not found")
    if revision.status not in {RevisionStatus.DRAFT, RevisionStatus.IN_REVIEW}:
        raise HTTPException(status_code=409, detail="Revision is not publishable")

    document = revision_document(revision)
    category = get_category_by_slug(db, document.category_slug)
    now = datetime.now(UTC)

    db.execute(
        update(GuideRevision)
        .where(
            GuideRevision.guide_id == guide.id,
            GuideRevision.status == RevisionStatus.PUBLISHED,
        )
        .values(status=RevisionStatus.SUPERSEDED)
    )
    revision.status = RevisionStatus.PUBLISHED
    revision.published_at = now
    guide.title = document.title
    guide.summary = document.summary
    guide.guide_type = document.guide_type
    guide.category_id = category.id
    guide.status = GuideStatus.PUBLISHED
    guide.current_revision_id = revision.id
    guide.published_at = now
    guide.archived_at = None
    replace_aliases(db, guide, document)
    db.flush()
    return revision


def archive_guide(db: Session, guide: Guide) -> None:
    guide = lock_guide(db, guide)
    guide.status = GuideStatus.ARCHIVED
    guide.archived_at = datetime.now(UTC)
    db.flush()


def published_guide_by_slug(db: Session, slug: str) -> Guide:
    guide = db.scalar(
        select(Guide).where(Guide.slug == slug, Guide.status == GuideStatus.PUBLISHED)
    )
    if guide is None:
        raise HTTPException(status_code=404, detail="Guide not found")
    return guide


def media_response(asset: MediaAsset, link: GuideMedia | None = None) -> MediaResponse:
    return MediaResponse(
        id=asset.id,
        link_id=link.id if link else None,
        kind=asset.kind,
        provider=asset.provider,
        url=public_media_url(asset.storage_key, asset.remote_url),
        source_page_url=asset.source_page_url,
        attribution=asset.attribution,
        license_name=asset.license_name,
        license_url=asset.license_url,
        alt_text=asset.alt_text,
        width=asset.width,
        height=asset.height,
        metadata=asset.extra_metadata,
        approval_status=asset.approval_status,
        role=link.role if link else None,
        caption=link.caption if link else None,
        sort_order=link.sort_order if link else None,
    )


def guide_detail(db: Session, guide: Guide) -> GuideDetail:
    if not guide.current_revision_id:
        raise HTTPException(status_code=404, detail="Published guide has no revision")
    revision = db.get(GuideRevision, guide.current_revision_id)
    if revision is None:
        raise HTTPException(status_code=500, detail="Published revision is missing")
    if revision.status != RevisionStatus.PUBLISHED:
        raise HTTPException(status_code=500, detail="Current revision is not published")
    document = revision_document(revision)
    aliases = list(
        db.scalars(
            select(GuideAlias.alias)
            .where(GuideAlias.guide_id == guide.id)
            .order_by(GuideAlias.alias)
        ).all()
    )
    sources = db.scalars(
        select(Source).where(Source.guide_revision_id == revision.id).order_by(Source.source_key)
    ).all()
    media_rows = db.execute(
        select(GuideMedia, MediaAsset)
        .join(MediaAsset, MediaAsset.id == GuideMedia.media_asset_id)
        .where(
            GuideMedia.guide_revision_id == revision.id,
            MediaAsset.approval_status == ApprovalStatus.APPROVED,
        )
        .order_by(GuideMedia.sort_order, GuideMedia.id)
    ).all()
    return GuideDetail(
        id=guide.id,
        revision_id=revision.id,
        revision_number=revision.revision_number,
        slug=guide.slug,
        title=guide.title,
        summary=guide.summary,
        guide_type=guide.guide_type,
        category=category_summary(get_guide_category(db, guide)),
        content=document.content.model_dump(mode="json"),
        aliases=aliases,
        sources=[
            SourceResponse(
                key=source.source_key,
                title=source.title,
                url=source.url,
                publisher=source.publisher,
                excerpt=source.excerpt,
                published_at=source.published_at,
                verified_at=source.verified_at,
            )
            for source in sources
        ],
        media=[media_response(asset, link) for link, asset in media_rows],
        published_at=guide.published_at,
        last_verified_at=document.last_verified_at,
    )
