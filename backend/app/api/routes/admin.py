import logging
import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Response
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import require_admin, require_editor
from app.db.models import (
    ApprovalStatus,
    Guide,
    GuideMedia,
    GuideRevision,
    GuideStatus,
    MediaAsset,
    ResearchJob,
    ResearchJobStatus,
    RevisionStatus,
    TopicRequest,
    User,
    UserRole,
)
from app.db.session import SessionLocal, get_db
from app.schemas.api import (
    AdminGuidePage,
    AdminGuideResponse,
    AiStatusResponse,
    GuideGenerateRequest,
    GuideMediaLinkCreate,
    GuidePublishRequest,
    GuideValidationResponse,
    MediaApprovalUpdate,
    MediaCreate,
    MediaResponse,
    ResearchJobComplete,
    ResearchJobCreate,
    ResearchJobPage,
    ResearchJobResponse,
    StockImageSearchResponse,
    TopicRequestAdminItem,
    TopicRequestAdminPage,
    UploadPresignRequest,
    UploadPresignResponse,
)
from app.schemas.content import GuideDocument
from app.services import stock
from app.services.audit import add_audit_log
from app.services.generation import queue_generation_job, run_generation_job
from app.services.guides import (
    admin_guide_response,
    archive_guide,
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
from app.services.storage import create_upload_presign
from app.services.text import normalize_text

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin", tags=["editor administration"])


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


@router.get("/topic-requests", response_model=TopicRequestAdminPage)
def list_topic_requests(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=settings.default_page_size, ge=1, le=settings.max_page_size),
    db: Session = Depends(get_db),
    _: User = Depends(require_editor),
) -> TopicRequestAdminPage:
    total = db.scalar(select(func.count()).select_from(TopicRequest)) or 0
    items = db.scalars(
        select(TopicRequest)
        .order_by(TopicRequest.request_count.desc(), TopicRequest.last_requested_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()
    return TopicRequestAdminPage(
        items=[TopicRequestAdminItem.model_validate(item) for item in items],
        pagination=pagination(page, page_size, total),
    )


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
    return AiStatusResponse(
        text_provider="openai",
        text_model=settings.openai_model,
        text_configured=settings.ai_configured,
        stock_provider=stock.PROVIDER,
        stock_configured=settings.stock_configured,
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


@router.get("/media/stock-search", response_model=StockImageSearchResponse)
def stock_search(
    q: str = Query(min_length=2, max_length=200),
    limit: int = Query(default=12, ge=1, le=40),
    _: User = Depends(require_editor),
) -> StockImageSearchResponse:
    try:
        results = stock.search_stock_images(q, limit=limit)
    except stock.StockSearchUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return StockImageSearchResponse(query=q, provider=stock.PROVIDER, results=results)
