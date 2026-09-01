import logging
import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Response
from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.auth_guard import admin_throttle
from app.core.config import settings
from app.core.security import require_admin, require_editor
from app.db.models import (
    ApprovalStatus,
    Category,
    Guide,
    GuideAlias,
    GuideMedia,
    GuideRevision,
    GuideStatus,
    MediaAsset,
    MediaKind,
    ResearchJob,
    ResearchJobStatus,
    RevisionStatus,
    Submission,
    SubmissionStatus,
    TopicRequest,
    User,
    UserRole,
)
from app.db.session import SessionLocal, get_db
from app.schemas.api import (
    AdminGuidePage,
    AdminGuideResponse,
    AiStatusResponse,
    CategoryCreate,
    CategoryResponse,
    CategoryUpdate,
    EditorCreate,
    EditorPasswordReset,
    EditorUpdate,
    GuideGenerateRequest,
    GuideMediaLinkCreate,
    GuidePublishRequest,
    GuideRegenerateRequest,
    GuideValidationResponse,
    ImageProviderInfo,
    ImageSearchResponse,
    MediaApprovalUpdate,
    MediaCreate,
    MediaResponse,
    ResearchJobComplete,
    ResearchJobCreate,
    ResearchJobPage,
    ResearchJobResponse,
    SubmissionAdminItem,
    SubmissionAdminPage,
    SubmissionDecision,
    TopicRequestAdminItem,
    TopicRequestAdminPage,
    UploadPresignRequest,
    UploadPresignResponse,
    UserResponse,
)
from app.schemas.content import GuideDocument
from app.services import images
from app.services import submissions as submission_service
from app.services.audit import add_audit_log
from app.services.generation import queue_generation_job, run_generation_job
from app.services.guides import (
    admin_guide_response,
    archive_guide,
    category_summary,
    create_guide,
    document_hash,
    get_category_by_slug,
    lock_guide,
    media_response,
    pagination,
    publish_revision,
    revision_document,
    save_draft,
    submit_for_review,
)
from app.services.passwords import WeakPassword, check_strength, hash_password
from app.services.sessions import revoke_all_for_user
from app.services.storage import create_upload_presign
from app.services.text import normalize_text

logger = logging.getLogger(__name__)

# Editor-or-better, and throttled, for the whole prefix rather than route by
# route. The per-route dependencies below stay — several of them narrow to
# admin — but nothing under /admin can be reached without a role even if a new
# endpoint is added and its author forgets. Deny is the default; each route
# opts into being *more* restricted, never less.
router = APIRouter(
    prefix="/admin",
    tags=["editor administration"],
    dependencies=[Depends(admin_throttle), Depends(require_editor)],
)


def run_generation_in_background(job_id: uuid.UUID) -> None:
    """Background tasks outlive the request, so they need a session of their own."""
    with SessionLocal() as session:
        try:
            run_generation_job(session, job_id)
        except Exception:  # noqa: BLE001 - a background crash must not stay silent
            logger.exception("Generation job %s crashed", job_id)


def guide_or_404(db: Session, guide_id: uuid.UUID) -> Guide:
    guide = db.get(Guide, guide_id)
    if guide is None:
        raise HTTPException(status_code=404, detail="Guide not found")
    return guide


def revision_or_404(db: Session, guide: Guide, revision_id: uuid.UUID) -> GuideRevision:
    revision = db.scalar(
        select(GuideRevision).where(
            GuideRevision.id == revision_id, GuideRevision.guide_id == guide.id
        )
    )
    if revision is None:
        raise HTTPException(status_code=404, detail="Guide revision not found")
    return revision


def latest_editable_revision(db: Session, guide: Guide) -> GuideRevision:
    revision = db.scalar(
        select(GuideRevision)
        .where(
            GuideRevision.guide_id == guide.id,
            GuideRevision.status.in_([RevisionStatus.DRAFT, RevisionStatus.IN_REVIEW]),
        )
        .order_by(GuideRevision.revision_number.desc())
        .with_for_update()
        .limit(1)
    )
    if revision is None:
        raise HTTPException(status_code=409, detail="Guide has no editable draft")
    return revision


def research_job_for_update(db: Session, job_id: uuid.UUID) -> ResearchJob:
    job = db.scalar(select(ResearchJob).where(ResearchJob.id == job_id).with_for_update())
    if job is None:
        raise HTTPException(status_code=404, detail="Research job not found")
    return job


def mark_draft_changed(guide: Guide, revision: GuideRevision) -> None:
    revision.status = RevisionStatus.DRAFT
    guide.updated_at = datetime.now(UTC)
    if guide.current_revision_id is None:
        guide.status = GuideStatus.DRAFT


@router.get("/guides", response_model=AdminGuidePage)
def list_admin_guides(
    guide_status: GuideStatus | None = Query(default=None, alias="status"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=settings.default_page_size, ge=1, le=settings.max_page_size),
    db: Session = Depends(get_db),
    _: User = Depends(require_editor),
) -> AdminGuidePage:
    query = select(Guide)
    if guide_status:
        query = query.where(Guide.status == guide_status)
    total = db.scalar(select(func.count()).select_from(query.subquery())) or 0
    guides = db.scalars(
        query.order_by(Guide.updated_at.desc()).offset((page - 1) * page_size).limit(page_size)
    ).all()
    return AdminGuidePage(
        items=[admin_guide_response(db, guide) for guide in guides],
        pagination=pagination(page, page_size, total),
    )


@router.post("/guides", response_model=AdminGuideResponse, status_code=201)
def create_admin_guide(
    document: GuideDocument,
    db: Session = Depends(get_db),
    user: User = Depends(require_editor),
) -> AdminGuideResponse:
    try:
        guide = create_guide(db, document, user)
        add_audit_log(db, user, "guide.created", "guide", guide.id)
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="Guide slug already exists") from exc
    return admin_guide_response(db, guide)


@router.post("/guides/import", response_model=AdminGuideResponse)
def import_guide_document(
    document: GuideDocument,
    publish: bool = Query(default=False),
    db: Session = Depends(get_db),
    user: User = Depends(require_editor),
) -> AdminGuideResponse:
    if publish and user.role != UserRole.ADMIN:
        raise HTTPException(status_code=403, detail="Administrator role required to publish")
    try:
        guide = db.scalar(select(Guide).where(Guide.slug == document.slug))
        if guide is None:
            guide = create_guide(db, document, user)
            revision = latest_editable_revision(db, guide)
        else:
            revision = save_draft(db, guide, document, user)
        if publish:
            revision = publish_revision(db, guide, revision.id)
        add_audit_log(
            db,
            user,
            "guide.imported",
            "guide",
            guide.id,
            {"published": publish, "revision_id": str(revision.id)},
        )
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=409, detail="Guide import conflicts with existing data"
        ) from exc
    return admin_guide_response(db, guide)


@router.get("/guides/{guide_id}", response_model=AdminGuideResponse)
def get_admin_guide(
    guide_id: uuid.UUID,
    db: Session = Depends(get_db),
    _: User = Depends(require_editor),
) -> AdminGuideResponse:
    return admin_guide_response(db, guide_or_404(db, guide_id))


@router.put("/guides/{guide_id}/draft", response_model=AdminGuideResponse)
def replace_guide_draft(
    guide_id: uuid.UUID,
    document: GuideDocument,
    db: Session = Depends(get_db),
    user: User = Depends(require_editor),
) -> AdminGuideResponse:
    guide = guide_or_404(db, guide_id)
    revision = save_draft(db, guide, document, user)
    add_audit_log(
        db,
        user,
        "guide.draft_saved",
        "guide",
        guide.id,
        {"revision_id": str(revision.id)},
    )
    db.commit()
    return admin_guide_response(db, guide)


@router.post("/guides/{guide_id}/validate", response_model=GuideValidationResponse)
def validate_guide_draft(
    guide_id: uuid.UUID,
    db: Session = Depends(get_db),
    _: User = Depends(require_editor),
) -> GuideValidationResponse:
    guide = guide_or_404(db, guide_id)
    revision = latest_editable_revision(db, guide)
    document = revision_document(revision)
    return GuideValidationResponse(
        valid=True, content_hash=document_hash(document), document=document
    )


@router.post("/guides/{guide_id}/submit-for-review", response_model=AdminGuideResponse)
def submit_guide_for_review(
    guide_id: uuid.UUID,
    db: Session = Depends(get_db),
    user: User = Depends(require_editor),
) -> AdminGuideResponse:
    guide = guide_or_404(db, guide_id)
    revision = submit_for_review(db, guide)
    add_audit_log(
        db,
        user,
        "guide.submitted_for_review",
        "guide",
        guide.id,
        {"revision_id": str(revision.id)},
    )
    db.commit()
    return admin_guide_response(db, guide)


@router.post("/guides/{guide_id}/publish", response_model=AdminGuideResponse)
def publish_guide(
    guide_id: uuid.UUID,
    payload: GuidePublishRequest,
    db: Session = Depends(get_db),
    user: User = Depends(require_admin),
) -> AdminGuideResponse:
    guide = guide_or_404(db, guide_id)
    revision = publish_revision(db, guide, payload.revision_id)
    add_audit_log(
        db,
        user,
        "guide.published",
        "guide",
        guide.id,
        {"revision_id": str(revision.id)},
    )
    db.commit()
    return admin_guide_response(db, guide)


@router.post("/guides/{guide_id}/archive", status_code=204)
def archive_admin_guide(
    guide_id: uuid.UUID,
    db: Session = Depends(get_db),
    user: User = Depends(require_admin),
) -> Response:
    guide = guide_or_404(db, guide_id)
    archive_guide(db, guide)
    add_audit_log(db, user, "guide.archived", "guide", guide.id)
    db.commit()
    return Response(status_code=204)


@router.get("/guides/{guide_id}/export", response_model=GuideDocument)
def export_guide_document(
    guide_id: uuid.UUID,
    revision_id: uuid.UUID | None = None,
    db: Session = Depends(get_db),
    _: User = Depends(require_editor),
) -> GuideDocument:
    guide = guide_or_404(db, guide_id)
    selected_revision: GuideRevision | None
    if revision_id:
        selected_revision = revision_or_404(db, guide, revision_id)
    else:
        selected_revision = db.scalar(
            select(GuideRevision)
            .where(GuideRevision.guide_id == guide.id)
            .order_by(GuideRevision.revision_number.desc())
            .limit(1)
        )
        if selected_revision is None:
            raise HTTPException(status_code=404, detail="Guide has no revisions")
    return revision_document(selected_revision)


@router.get("/media", response_model=list[MediaResponse])
def list_media(
    approval_status: ApprovalStatus | None = Query(default=None, alias="status"),
    limit: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
    _: User = Depends(require_editor),
) -> list[MediaResponse]:
    query = select(MediaAsset)
    if approval_status:
        query = query.where(MediaAsset.approval_status == approval_status)
    assets = db.scalars(query.order_by(MediaAsset.created_at.desc()).limit(limit)).all()
    return [media_response(asset) for asset in assets]


@router.post("/media", response_model=MediaResponse, status_code=201)
def create_media(
    payload: MediaCreate,
    db: Session = Depends(get_db),
    user: User = Depends(require_editor),
) -> MediaResponse:
    asset = MediaAsset(
        kind=payload.kind,
        provider=payload.provider,
        remote_url=str(payload.remote_url) if payload.remote_url else None,
        storage_key=payload.storage_key,
        source_page_url=str(payload.source_page_url) if payload.source_page_url else None,
        attribution=payload.attribution,
        license_name=payload.license_name,
        license_url=str(payload.license_url) if payload.license_url else None,
        alt_text=payload.alt_text,
        width=payload.width,
        height=payload.height,
        extra_metadata=payload.metadata,
        approval_status=payload.approval_status,
        created_by_user_id=user.id,
    )
    db.add(asset)
    db.flush()
    add_audit_log(db, user, "media.created", "media_asset", asset.id)
    db.commit()
    db.refresh(asset)
    return media_response(asset)


@router.patch("/media/{media_id}/approval", response_model=MediaResponse)
def update_media_approval(
    media_id: uuid.UUID,
    payload: MediaApprovalUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(require_editor),
) -> MediaResponse:
    asset = db.get(MediaAsset, media_id)
    if asset is None:
        raise HTTPException(status_code=404, detail="Media asset not found")
    asset.approval_status = payload.approval_status
    add_audit_log(
        db,
        user,
        "media.approval_changed",
        "media_asset",
        asset.id,
        {"status": payload.approval_status.value},
    )
    db.commit()
    db.refresh(asset)
    return media_response(asset)


@router.post("/media/uploads/presign", response_model=UploadPresignResponse)
def presign_media_upload(
    payload: UploadPresignRequest, _: User = Depends(require_editor)
) -> UploadPresignResponse:
    return create_upload_presign(payload)


@router.post("/guides/{guide_id}/draft/media", response_model=MediaResponse)
def link_media_to_draft(
    guide_id: uuid.UUID,
    payload: GuideMediaLinkCreate,
    db: Session = Depends(get_db),
    user: User = Depends(require_editor),
) -> MediaResponse:
    guide = guide_or_404(db, guide_id)
    guide = lock_guide(db, guide)
    asset = db.get(MediaAsset, payload.media_asset_id)
    if asset is None:
        raise HTTPException(status_code=404, detail="Media asset not found")

    try:
        revision = latest_editable_revision(db, guide)
    except HTTPException:
        if not guide.current_revision_id:
            raise
        current = db.get(GuideRevision, guide.current_revision_id)
        if current is None:
            raise HTTPException(
                status_code=500, detail="Published guide revision is missing"
            ) from None
        revision = save_draft(db, guide, revision_document(current), user)

    link = db.scalar(
        select(GuideMedia).where(
            GuideMedia.guide_revision_id == revision.id,
            GuideMedia.media_asset_id == asset.id,
            GuideMedia.role == payload.role,
        )
    )
    if link is None:
        link = GuideMedia(
            guide_revision_id=revision.id,
            media_asset_id=asset.id,
            role=payload.role,
        )
        db.add(link)
    link.caption = payload.caption
    link.sort_order = payload.sort_order
    mark_draft_changed(guide, revision)
    add_audit_log(
        db,
        user,
        "guide.media_linked",
        "guide",
        guide.id,
        {"media_asset_id": str(asset.id), "revision_id": str(revision.id)},
    )
    db.commit()
    return media_response(asset, link)


def draft_link(db: Session, guide: Guide, link_id: uuid.UUID) -> tuple[GuideRevision, GuideMedia]:
    """Find a placement on the editable draft, creating that draft if needed.

    The panel shows the published revision's media when there is no draft yet, so
    a link id can arrive pointing at published content. Editing it means making a
    draft first, exactly as placing a new image does; the copied placement is
    matched back by asset and role.
    """
    try:
        revision = latest_editable_revision(db, guide)
        link = db.scalar(
            select(GuideMedia).where(
                GuideMedia.id == link_id, GuideMedia.guide_revision_id == revision.id
            )
        )
        if link is not None:
            return revision, link
    except HTTPException:
        revision = None  # type: ignore[assignment]

    published_link = db.get(GuideMedia, link_id)
    if published_link is None:
        raise HTTPException(status_code=404, detail="Draft media link not found")

    if revision is None:
        current = db.get(
            GuideRevision, guide.current_revision_id or published_link.guide_revision_id
        )
        if current is None:
            raise HTTPException(status_code=409, detail="Guide has no editable draft")
        revision = save_draft(db, guide, revision_document(current), guide_author(db, guide))

    copied = db.scalar(
        select(GuideMedia).where(
            GuideMedia.guide_revision_id == revision.id,
            GuideMedia.media_asset_id == published_link.media_asset_id,
            GuideMedia.role == published_link.role,
        )
    )
    if copied is None:
        raise HTTPException(status_code=404, detail="Draft media link not found")
    return revision, copied


def guide_author(db: Session, guide: Guide) -> User:
    author = db.scalar(select(User).where(User.external_id == "system:seed"))
    if author is None:
        raise HTTPException(status_code=500, detail="No system author is available")
    return author


@router.post("/guides/{guide_id}/draft/media/{link_id}/swap", response_model=MediaResponse)
def swap_draft_media(
    guide_id: uuid.UUID,
    link_id: uuid.UUID,
    db: Session = Depends(get_db),
    user: User = Depends(require_editor),
) -> MediaResponse:
    """Put a different image in this slot, from the search that produced it.

    No model call: the asset remembers what was searched for and which results
    have already been shown, so this walks down the same list.
    """
    guide = lock_guide(db, guide_or_404(db, guide_id))
    revision, link = draft_link(db, guide, link_id)

    old_asset = db.get(MediaAsset, link.media_asset_id)
    if old_asset is None:
        raise HTTPException(status_code=404, detail="Media asset not found")

    metadata = dict(old_asset.extra_metadata or {})
    query = metadata.get("query") or metadata.get("subject") or old_asset.alt_text
    if not query:
        raise HTTPException(
            status_code=409, detail="This image records no search to repeat"
        )

    # Everything already offered for this slot, plus everything on the draft, so
    # a swap always moves forward instead of cycling back to the first result.
    tried: list[str] = [str(url) for url in metadata.get("tried") or []]
    tried.append(old_asset.remote_url or "")
    on_draft = set(
        db.scalars(
            select(MediaAsset.remote_url)
            .join(GuideMedia, GuideMedia.media_asset_id == MediaAsset.id)
            .where(GuideMedia.guide_revision_id == revision.id)
        ).all()
    )
    exclude = {url for url in [*tried, *on_draft] if url}

    document = revision_document(revision)
    results, problems = images.search_with_fallback(
        str(query),
        provider_id=old_asset.provider,
        guide_type=document.guide_type.value,
        category_slug=document.category_slug,
        limit=24,
    )
    candidate = next((item for item in results if item.remote_url not in exclude), None)
    if candidate is None:
        detail = f"No other image for {query!r}"
        if problems:
            detail += f". {problems[0]}"
        raise HTTPException(status_code=404, detail=detail)

    replacement = MediaAsset(
        kind=MediaKind.EXTERNAL if candidate.editorial_only else MediaKind.STOCK,
        provider=candidate.provider,
        remote_url=candidate.remote_url,
        source_page_url=candidate.source_page_url,
        attribution=candidate.attribution,
        license_name=candidate.license_name,
        license_url=candidate.license_url,
        alt_text=candidate.alt_text[:500],
        width=candidate.width,
        height=candidate.height,
        extra_metadata={
            "preview_url": candidate.preview_url,
            "subject": candidate.subject,
            "editorial_only": candidate.editorial_only,
            "query": query,
            "tried": [*tried, candidate.remote_url],
        },
        approval_status=old_asset.approval_status,
        created_by_user_id=user.id,
    )
    db.add(replacement)
    db.flush()

    link.media_asset_id = replacement.id
    link.caption = candidate.subject
    mark_draft_changed(guide, revision)

    # The image it replaced is not used anywhere else, so it is not worth keeping.
    still_used = db.scalar(
        select(func.count()).select_from(GuideMedia).where(
            GuideMedia.media_asset_id == old_asset.id
        )
    )
    if not still_used:
        db.delete(old_asset)

    add_audit_log(
        db,
        user,
        "guide.media_swapped",
        "guide",
        guide.id,
        {"query": str(query), "provider": candidate.provider},
    )
    db.commit()
    return media_response(replacement, link)


@router.delete("/guides/{guide_id}/draft/media/{link_id}", status_code=204)
def unlink_media_from_draft(
    guide_id: uuid.UUID,
    link_id: uuid.UUID,
    db: Session = Depends(get_db),
    user: User = Depends(require_editor),
) -> Response:
    guide = guide_or_404(db, guide_id)
    guide = lock_guide(db, guide)
    revision = latest_editable_revision(db, guide)
    link = db.scalar(
        select(GuideMedia).where(
            GuideMedia.id == link_id, GuideMedia.guide_revision_id == revision.id
        )
    )
    if link is None:
        raise HTTPException(status_code=404, detail="Draft media link not found")
    db.delete(link)
    mark_draft_changed(guide, revision)
    add_audit_log(db, user, "guide.media_unlinked", "guide", guide.id)
    db.commit()
    return Response(status_code=204)


def topic_already_written():
    """True when a published guide now answers this request.

    The backlog is meant to be work, so a topic somebody has since written stops
    being a request. Matching mirrors POST /topic-requests: the normalized topic
    as a slug, or any of the guide's aliases.
    """
    # Two flat EXISTS rather than one nested inside another: nesting let
    # SQLAlchemy put topic_requests in the inner FROM instead of correlating it,
    # which asked "does any topic match any alias" and hid the whole backlog.
    by_slug = (
        select(Guide.id)
        .where(
            Guide.status == GuideStatus.PUBLISHED,
            Guide.slug == func.replace(TopicRequest.normalized_topic, " ", "-"),
        )
        .correlate(TopicRequest)
        .exists()
    )
    by_alias = (
        select(GuideAlias.id)
        .join(Guide, Guide.id == GuideAlias.guide_id)
        .where(
            Guide.status == GuideStatus.PUBLISHED,
            GuideAlias.normalized_alias == TopicRequest.normalized_topic,
        )
        .correlate(TopicRequest)
        .exists()
    )
    return or_(by_slug, by_alias)


@router.get("/topic-requests", response_model=TopicRequestAdminPage)
def list_topic_requests(
    include_written: bool = Query(default=False),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=settings.default_page_size, ge=1, le=settings.max_page_size),
    db: Session = Depends(get_db),
    _: User = Depends(require_editor),
) -> TopicRequestAdminPage:
    query = select(TopicRequest)
    if not include_written:
        query = query.where(~topic_already_written())

    total = db.scalar(select(func.count()).select_from(query.subquery())) or 0
    items = db.scalars(
        query.order_by(TopicRequest.request_count.desc(), TopicRequest.last_requested_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()
    return TopicRequestAdminPage(
        items=[TopicRequestAdminItem.model_validate(item) for item in items],
        pagination=pagination(page, page_size, total),
    )


@router.delete("/topic-requests/{request_id}", status_code=204)
def dismiss_topic_request(
    request_id: uuid.UUID,
    db: Session = Depends(get_db),
    user: User = Depends(require_editor),
) -> Response:
    """Drop a request from the backlog. Idempotent, so a double click is harmless."""
    topic_request = db.get(TopicRequest, request_id)
    if topic_request is not None:
        add_audit_log(
            db,
            user,
            "topic_request.dismissed",
            "topic_request",
            topic_request.id,
            {"topic": topic_request.topic},
        )
        db.delete(topic_request)
        db.commit()
    return Response(status_code=204)


@router.get("/research-jobs", response_model=ResearchJobPage)
def list_research_jobs(
    job_status: ResearchJobStatus | None = Query(default=None, alias="status"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=settings.default_page_size, ge=1, le=settings.max_page_size),
    db: Session = Depends(get_db),
    _: User = Depends(require_editor),
) -> ResearchJobPage:
    query = select(ResearchJob)
    if job_status:
        query = query.where(ResearchJob.status == job_status)
    total = db.scalar(select(func.count()).select_from(query.subquery())) or 0
    items = db.scalars(
        query.order_by(ResearchJob.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()
    return ResearchJobPage(
        items=[ResearchJobResponse.model_validate(item) for item in items],
        pagination=pagination(page, page_size, total),
    )


@router.post("/research-jobs", response_model=ResearchJobResponse, status_code=202)
def create_research_job(
    payload: ResearchJobCreate,
    db: Session = Depends(get_db),
    user: User = Depends(require_editor),
) -> ResearchJob:
    job = ResearchJob(
        topic=payload.topic.strip(),
        normalized_topic=normalize_text(payload.topic),
        guide_type=payload.guide_type,
        instructions=payload.instructions,
        provider_config=payload.provider_config,
        requested_by_user_id=user.id,
    )
    db.add(job)
    db.flush()
    add_audit_log(db, user, "research_job.queued", "research_job", job.id)
    db.commit()
    db.refresh(job)
    return job


@router.get("/research-jobs/{job_id}", response_model=ResearchJobResponse)
def get_research_job(
    job_id: uuid.UUID,
    db: Session = Depends(get_db),
    _: User = Depends(require_editor),
) -> ResearchJob:
    job = db.get(ResearchJob, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Research job not found")
    return job


@router.post("/research-jobs/{job_id}/retry", response_model=ResearchJobResponse)
def retry_research_job(
    job_id: uuid.UUID,
    db: Session = Depends(get_db),
    user: User = Depends(require_editor),
) -> ResearchJob:
    job = research_job_for_update(db, job_id)
    if job.status not in {ResearchJobStatus.FAILED, ResearchJobStatus.CANCELLED}:
        raise HTTPException(status_code=409, detail="Only failed or cancelled jobs can be retried")
    job.status = ResearchJobStatus.QUEUED
    job.error_message = None
    job.started_at = None
    job.finished_at = None
    add_audit_log(db, user, "research_job.retried", "research_job", job.id)
    db.commit()
    db.refresh(job)
    return job


@router.post("/research-jobs/{job_id}/start", response_model=ResearchJobResponse)
def start_research_job(
    job_id: uuid.UUID,
    db: Session = Depends(get_db),
    user: User = Depends(require_editor),
) -> ResearchJob:
    job = research_job_for_update(db, job_id)
    if job.status != ResearchJobStatus.QUEUED:
        raise HTTPException(status_code=409, detail="Only queued jobs can be started")
    job.status = ResearchJobStatus.RUNNING
    job.started_at = datetime.now(UTC)
    job.attempt_count += 1
    add_audit_log(db, user, "research_job.started", "research_job", job.id)
    db.commit()
    db.refresh(job)
    return job


@router.post("/research-jobs/{job_id}/cancel", response_model=ResearchJobResponse)
def cancel_research_job(
    job_id: uuid.UUID,
    db: Session = Depends(get_db),
    user: User = Depends(require_editor),
) -> ResearchJob:
    job = research_job_for_update(db, job_id)
    if job.status not in {ResearchJobStatus.QUEUED, ResearchJobStatus.RUNNING}:
        raise HTTPException(status_code=409, detail="Job cannot be cancelled in its current state")
    job.status = ResearchJobStatus.CANCELLED
    job.finished_at = datetime.now(UTC)
    add_audit_log(db, user, "research_job.cancelled", "research_job", job.id)
    db.commit()
    db.refresh(job)
    return job


@router.post("/research-jobs/{job_id}/complete", response_model=ResearchJobResponse)
def complete_research_job(
    job_id: uuid.UUID,
    payload: ResearchJobComplete,
    db: Session = Depends(get_db),
    user: User = Depends(require_editor),
) -> ResearchJob:
    job = research_job_for_update(db, job_id)
    target_status = ResearchJobStatus(payload.status)
    allowed_sources = {
        ResearchJobStatus.REVIEW: {ResearchJobStatus.RUNNING},
        ResearchJobStatus.FAILED: {ResearchJobStatus.RUNNING},
        ResearchJobStatus.COMPLETED: {
            ResearchJobStatus.RUNNING,
            ResearchJobStatus.REVIEW,
        },
    }
    if job.status not in allowed_sources[target_status]:
        raise HTTPException(
            status_code=409,
            detail=f"A {job.status.value} job cannot transition to {target_status.value}",
        )
    if target_status == ResearchJobStatus.FAILED and not payload.error_message:
        raise HTTPException(status_code=422, detail="Failed jobs require error_message")
    job.status = target_status
    job.result = payload.result
    job.error_message = payload.error_message
    job.estimated_cost_micros = payload.estimated_cost_micros
    job.finished_at = datetime.now(UTC)
    add_audit_log(
        db,
        user,
        "research_job.completed",
        "research_job",
        job.id,
        {"status": target_status.value},
    )
    db.commit()
    db.refresh(job)
    return job


@router.get("/ai/status", response_model=AiStatusResponse)
def ai_status(_: User = Depends(require_editor)) -> AiStatusResponse:
    """What the admin panel checks before it offers the generate button."""
    providers = [ImageProviderInfo(**item) for item in images.available_providers()]
    return AiStatusResponse(
        text_provider="openai",
        text_model=settings.openai_model,
        text_configured=settings.ai_configured,
        image_providers=providers,
        images_configured=any(provider.configured for provider in providers),
        storage_configured=settings.storage_configured,
    )


@router.post("/ai/generate", response_model=ResearchJobResponse, status_code=202)
def generate_guide(
    payload: GuideGenerateRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    user: User = Depends(require_editor),
) -> ResearchJob:
    """Queue one topic for generation and start it immediately.

    The response is the job row. The admin panel polls `/admin/research-jobs/{id}`
    until the status leaves `queued`/`running`, then opens `created_guide_id`.
    """
    if not settings.ai_configured:
        raise HTTPException(
            status_code=503,
            detail="Guide generation is not configured. Set OPENAI_API_KEY.",
        )
    if payload.category_slug:
        get_category_by_slug(db, payload.category_slug)

    job = queue_generation_job(
        db,
        topic=payload.topic,
        guide_type=payload.guide_type,
        entry_type=payload.entry_type,
        category_slug=payload.category_slug,
        instructions=payload.instructions,
        attach_images=payload.attach_images,
        user=user,
    )
    background_tasks.add_task(run_generation_in_background, job.id)
    return job


@router.post(
    "/guides/{guide_id}/regenerate", response_model=ResearchJobResponse, status_code=202
)
def regenerate_guide(
    guide_id: uuid.UUID,
    payload: GuideRegenerateRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    user: User = Depends(require_editor),
) -> ResearchJob:
    """Rewrite an existing guide from its own title, as a draft.

    The published revision is untouched until somebody publishes the new draft.
    An editable draft, however, is replaced: that is the point of the button.
    """
    if not settings.ai_configured:
        raise HTTPException(
            status_code=503,
            detail="Guide generation is not configured. Set OPENAI_API_KEY.",
        )

    guide = guide_or_404(db, guide_id)
    source = db.get(GuideRevision, guide.current_revision_id) if guide.current_revision_id else None
    if source is None:
        source = db.scalar(
            select(GuideRevision)
            .where(GuideRevision.guide_id == guide.id)
            .order_by(GuideRevision.revision_number.desc())
            .limit(1)
        )
    if source is None:
        raise HTTPException(status_code=409, detail="This guide has no revision to rewrite")

    document = revision_document(source)
    job = queue_generation_job(
        db,
        topic=document.title,
        guide_type=document.guide_type,
        entry_type=document.content.larp.entry_type,
        category_slug=document.category_slug,
        instructions=payload.instructions,
        attach_images=payload.attach_images,
        user=user,
        guide_id=guide.id,
        replace_images=payload.replace_images,
    )
    add_audit_log(db, user, "guide.regenerate_queued", "guide", guide.id, {"job_id": str(job.id)})
    db.commit()
    background_tasks.add_task(run_generation_in_background, job.id)
    return job


@router.post("/research-jobs/{job_id}/run", response_model=ResearchJobResponse, status_code=202)
def run_research_job(
    job_id: uuid.UUID,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    _: User = Depends(require_editor),
) -> ResearchJob:
    """Run a queued job now, instead of waiting for an external worker to claim it."""
    job = db.get(ResearchJob, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Research job not found")
    if job.status != ResearchJobStatus.QUEUED:
        raise HTTPException(status_code=409, detail="Only queued jobs can be run")
    background_tasks.add_task(run_generation_in_background, job.id)
    return job


@router.get("/media/providers", response_model=list[ImageProviderInfo])
def list_image_providers(_: User = Depends(require_editor)) -> list[ImageProviderInfo]:
    """Which image sources this deployment can reach, and what each is good for."""
    return [ImageProviderInfo(**item) for item in images.available_providers()]


@router.get("/media/image-search", response_model=ImageSearchResponse)
def image_search(
    q: str = Query(min_length=2, max_length=200),
    provider: str = Query(default="auto"),
    guide_type: str | None = Query(default=None),
    category: str | None = Query(default=None),
    limit: int = Query(default=12, ge=1, le=40),
    _: User = Depends(require_editor),
) -> ImageSearchResponse:
    """Search one provider, or let `auto` pick from the guide's category."""
    if provider not in {"auto", ""} and provider not in images.PROVIDERS:
        raise HTTPException(status_code=422, detail=f"Unknown image provider: {provider}")

    results, warnings = images.search_with_fallback(
        q, provider_id=provider, guide_type=guide_type, category_slug=category, limit=limit
    )
    if not results and warnings:
        raise HTTPException(status_code=503, detail="; ".join(warnings[:3]))
    return ImageSearchResponse(
        query=q,
        provider=results[0].provider if results else provider,
        results=results,
        warnings=warnings,
    )


# ---------------------------------------------------------------- submissions


def submission_admin_item(db: Session, submission: Submission) -> SubmissionAdminItem:
    category = db.get(Category, submission.category_id) if submission.category_id else None
    return SubmissionAdminItem(
        id=submission.id,
        topic=submission.topic,
        normalized_topic=submission.normalized_topic,
        notes=submission.notes,
        guide_type=submission.guide_type,
        entry_type=submission.entry_type,
        category=category_summary(category) if category else None,
        suggested_category=submission.suggested_category,
        credit_name=submission.credit_name,
        status=submission.status,
        screening=submission.screening,
        review_notes=submission.review_notes,
        created_guide_id=submission.created_guide_id,
        reviewed_at=submission.reviewed_at,
        created_at=submission.created_at,
        client_hash=submission.client_hash,
    )


@router.get("/submissions", response_model=SubmissionAdminPage)
def list_submissions(
    submission_status: SubmissionStatus | None = Query(default=None, alias="status"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=settings.default_page_size, ge=1, le=settings.max_page_size),
    db: Session = Depends(get_db),
    _: User = Depends(require_editor),
) -> SubmissionAdminPage:
    query = select(Submission)
    if submission_status:
        query = query.where(Submission.status == submission_status)
    total = db.scalar(select(func.count()).select_from(query.subquery())) or 0
    items = db.scalars(
        query.order_by(Submission.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()
    return SubmissionAdminPage(
        items=[submission_admin_item(db, item) for item in items],
        pagination=pagination(page, page_size, total),
    )


@router.post("/submissions/{submission_id}/review", response_model=SubmissionAdminItem)
def review_submission(
    submission_id: uuid.UUID,
    generate: bool = Query(default=True),
    db: Session = Depends(get_db),
    user: User = Depends(require_editor),
) -> SubmissionAdminItem:
    """Screen it, and write the draft when it passes.

    This is where a submission first costs money, which is why it is an editor
    pressing a button rather than anything an anonymous request can reach.
    """
    if not settings.ai_configured:
        raise HTTPException(status_code=503, detail="Review needs a model. Set OPENAI_API_KEY.")

    submission = submission_service.submission_or_404(db, submission_id)
    if submission.status in {SubmissionStatus.ACCEPTED, SubmissionStatus.SPAM}:
        raise HTTPException(status_code=409, detail="This submission is already settled")

    reviewed = submission_service.review_submission(db, submission, user, generate=generate)
    add_audit_log(
        db,
        user,
        "submission.reviewed",
        "submission",
        reviewed.id,
        {"status": reviewed.status.value},
    )
    db.commit()
    return submission_admin_item(db, reviewed)


@router.post("/submissions/{submission_id}/accept", response_model=SubmissionAdminItem)
def accept_submission(
    submission_id: uuid.UUID,
    payload: SubmissionDecision,
    db: Session = Depends(get_db),
    user: User = Depends(require_admin),
) -> SubmissionAdminItem:
    """Mark it accepted. Publishing the draft it produced is still a separate act."""
    submission = submission_service.submission_or_404(db, submission_id)
    if submission.created_guide_id is None:
        raise HTTPException(
            status_code=409, detail="Nothing has been drafted from this submission yet"
        )
    updated = submission_service.set_status(
        db, submission, SubmissionStatus.ACCEPTED, user, payload.review_notes
    )
    add_audit_log(db, user, "submission.accepted", "submission", updated.id)
    db.commit()
    return submission_admin_item(db, updated)


@router.post("/submissions/{submission_id}/reject", response_model=SubmissionAdminItem)
def reject_submission(
    submission_id: uuid.UUID,
    payload: SubmissionDecision,
    db: Session = Depends(get_db),
    user: User = Depends(require_editor),
) -> SubmissionAdminItem:
    """Turn it down, and optionally stop that client sending more."""
    submission = submission_service.submission_or_404(db, submission_id)
    new_status = SubmissionStatus.SPAM if payload.block_client else SubmissionStatus.REJECTED
    updated = submission_service.set_status(
        db, submission, new_status, user, payload.review_notes
    )
    if payload.block_client:
        submission_service.block_client(
            db, updated.client_hash, user, payload.review_notes or "Marked as spam"
        )
    add_audit_log(
        db,
        user,
        "submission.rejected",
        "submission",
        updated.id,
        {"blocked": payload.block_client},
    )
    db.commit()
    return submission_admin_item(db, updated)


# ---------------------------------------------------------------- categories


@router.post("/categories", response_model=CategoryResponse, status_code=201)
def create_category(
    payload: CategoryCreate,
    db: Session = Depends(get_db),
    user: User = Depends(require_admin),
) -> CategoryResponse:
    """Promote a reader's suggested category into a real one."""
    category = submission_service.promote_category(
        db, payload.name, user, payload.description, payload.sort_order
    )
    add_audit_log(db, user, "category.created", "category", category.id, {"slug": category.slug})
    db.commit()
    return CategoryResponse(
        id=category.id,
        slug=category.slug,
        title=category.title,
        description=category.description,
        sort_order=category.sort_order,
        published_guide_count=0,
    )


@router.patch("/categories/{category_id}", response_model=CategoryResponse)
def update_category(
    category_id: uuid.UUID,
    payload: CategoryUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(require_admin),
) -> CategoryResponse:
    category = db.get(Category, category_id)
    if category is None:
        raise HTTPException(status_code=404, detail="Category not found")
    for field, value in payload.model_dump(exclude_none=True).items():
        setattr(category, field, value)
    add_audit_log(db, user, "category.updated", "category", category.id)
    db.commit()
    db.refresh(category)
    published = db.scalar(
        select(func.count())
        .select_from(Guide)
        .where(Guide.category_id == category.id, Guide.status == GuideStatus.PUBLISHED)
    )
    return CategoryResponse(
        id=category.id,
        slug=category.slug,
        title=category.title,
        description=category.description,
        sort_order=category.sort_order,
        published_guide_count=published or 0,
    )


# ------------------------------------------------------------------- editors
#
# Accounts are made here or from the CLI, and nowhere else. There is no
# registration endpoint, so the only way to get an account is for somebody who
# already has an admin one to make it.


def editor_or_404(db: Session, user_id: uuid.UUID) -> User:
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="Account not found")
    return user


@router.get("/editors", response_model=list[UserResponse])
def list_editors(
    db: Session = Depends(get_db), _: User = Depends(require_admin)
) -> list[User]:
    return list(db.scalars(select(User).order_by(User.created_at.desc())).all())


@router.post("/editors", response_model=UserResponse, status_code=201)
def create_editor(
    payload: EditorCreate,
    db: Session = Depends(get_db),
    actor: User = Depends(require_admin),
) -> User:
    email = payload.email.strip().lower()
    try:
        check_strength(payload.password, email=email)
    except WeakPassword as weak:
        raise HTTPException(status_code=422, detail=str(weak)) from weak

    if db.scalar(select(User).where(User.email == email)) is not None:
        raise HTTPException(status_code=409, detail="An account already uses that address")

    user = User(
        email=email,
        display_name=payload.display_name,
        role=payload.role,
        password_hash=hash_password(payload.password),
        password_updated_at=datetime.now(UTC),
    )
    db.add(user)
    db.flush()
    add_audit_log(db, actor, "editor.created", "user", user.id, {"role": payload.role.value})
    db.commit()
    db.refresh(user)
    return user


@router.patch("/editors/{user_id}", response_model=UserResponse)
def update_editor(
    user_id: uuid.UUID,
    payload: EditorUpdate,
    db: Session = Depends(get_db),
    actor: User = Depends(require_admin),
) -> User:
    user = editor_or_404(db, user_id)

    # Demoting or disabling yourself is how a deployment ends up with no
    # administrator and no way to make one without the CLI.
    demoting = payload.role not in (None, UserRole.ADMIN)
    if user.id == actor.id and (demoting or payload.is_active is False):
        raise HTTPException(
            status_code=409,
            detail="You cannot remove your own administrator access. Ask another admin.",
        )

    if payload.role is not None:
        user.role = payload.role
    if payload.is_active is not None:
        user.is_active = payload.is_active
        if not payload.is_active:
            # A disabled account with a live session is still signed in.
            revoke_all_for_user(db, user)

    add_audit_log(
        db,
        actor,
        "editor.updated",
        "user",
        user.id,
        {"role": user.role.value, "is_active": user.is_active},
    )
    db.commit()
    db.refresh(user)
    return user


@router.post("/editors/{user_id}/password", status_code=204)
def reset_editor_password(
    user_id: uuid.UUID,
    payload: EditorPasswordReset,
    db: Session = Depends(get_db),
    actor: User = Depends(require_admin),
) -> Response:
    """For a locked-out editor. Ends every session that account has.

    An admin can set a password but cannot read one, and this is deliberately
    not the route for changing your own - that one asks for the current
    password, which is what stops a borrowed unlocked laptop being permanent.
    """
    user = editor_or_404(db, user_id)
    try:
        check_strength(payload.password, email=user.email)
    except WeakPassword as weak:
        raise HTTPException(status_code=422, detail=str(weak)) from weak

    user.password_hash = hash_password(payload.password)
    user.password_updated_at = datetime.now(UTC)
    ended = revoke_all_for_user(db, user)
    add_audit_log(db, actor, "editor.password_reset", "user", user.id, {"sessions_ended": ended})
    db.commit()
    return Response(status_code=204)
