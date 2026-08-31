"""The end-to-end generate-a-guide pipeline.

Topic -> model -> validated document -> draft revision -> illustrated.
Nothing here publishes: the last step of every run is a draft waiting for an editor.
"""

import uuid
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.models import (
    ApprovalStatus,
    Category,
    EntryType,
    Guide,
    GuideMedia,
    GuideRevision,
    GuideType,
    MediaAsset,
    MediaKind,
    ResearchJob,
    ResearchJobStatus,
    RevisionStatus,
    User,
)
from app.schemas.api import ImageCandidate
from app.schemas.content import GuideDocument
from app.services import ai, images
from app.services.audit import add_audit_log
from app.services.guides import create_guide, save_draft
from app.services.text import normalize_text, slugify

HERO_ROLE = "hero"
GALLERY_ROLE = "gallery"


def active_category_slugs(db: Session) -> list[str]:
    return list(
        db.scalars(
            select(Category.slug)
            .where(Category.is_active.is_(True))
            .order_by(Category.sort_order, Category.slug)
        ).all()
    )


def latest_editable_revision(db: Session, guide: Guide) -> GuideRevision | None:
    return db.scalar(
        select(GuideRevision)
        .where(
            GuideRevision.guide_id == guide.id,
            GuideRevision.status.in_([RevisionStatus.DRAFT, RevisionStatus.IN_REVIEW]),
        )
        .order_by(GuideRevision.revision_number.desc())
        .limit(1)
    )


def store_document_as_draft(
    db: Session, document: GuideDocument, author: User
) -> tuple[Guide, GuideRevision]:
    """Create the guide, or add a draft revision when the slug already exists."""
    guide = db.scalar(select(Guide).where(Guide.slug == document.slug))
    if guide is None:
        guide = create_guide(db, document, author)
        revision = latest_editable_revision(db, guide)
        if revision is None:
            raise RuntimeError("New guide revision was not created")
        return guide, revision
    return guide, save_draft(db, guide, document, author)


def attach_images(
    db: Session,
    revision: GuideRevision,
    results: list[tuple[ImageCandidate, str]],
    author: User,
    queries: dict[str, str] | None = None,
    *,
    start_order: int = 0,
    approve: bool = False,
) -> list[tuple[MediaAsset, GuideMedia]]:
    """Register each photo as a media asset and place it on the draft revision.

    Assets land in `draft` approval state on purpose. Public guide pages only render
    approved media, so a generated guide never ships an image nobody has looked at.
    """
    placed: list[tuple[MediaAsset, GuideMedia]] = []
    for offset, (result, role) in enumerate(results):
        index = start_order + offset
        asset = MediaAsset(
            kind=MediaKind.STOCK if not result.editorial_only else MediaKind.EXTERNAL,
            provider=result.provider,
            remote_url=result.remote_url,
            source_page_url=result.source_page_url,
            attribution=result.attribution,
            license_name=result.license_name,
            license_url=result.license_url,
            alt_text=result.alt_text[:500],
            width=result.width,
            height=result.height,
            extra_metadata={
                "preview_url": result.preview_url,
                "subject": result.subject,
                "editorial_only": result.editorial_only,
                # What was searched for, so the panel can ask for a different
                # answer to the same question without calling the model again.
                "query": (queries or {}).get(result.remote_url),
                "tried": [result.remote_url],
            },
            approval_status=ApprovalStatus.APPROVED if approve else ApprovalStatus.DRAFT,
            created_by_user_id=author.id,
        )
        db.add(asset)
        db.flush()
        link = GuideMedia(
            guide_revision_id=revision.id,
            media_asset_id=asset.id,
            role=role or (HERO_ROLE if index == 0 else GALLERY_ROLE),
            sort_order=index,
            caption=result.subject,
        )
        db.add(link)
        db.flush()
        placed.append((asset, link))
    return placed


def fetch_planned_images(
    document: GuideDocument, *, limit: int = 6
) -> tuple[list[tuple[ImageCandidate, str]], list[str], dict[str, str]]:
    """Run the guide's own image brief through the provider registry."""
    picked: list[tuple[ImageCandidate, str]] = []
    warnings: list[str] = []
    seen: set[str] = set()
    queries: dict[str, str] = {}

    for item in ai.image_plan(document, limit=limit):
        results, problems = images.search_with_fallback(
            item.query,
            provider_id=item.provider,
            guide_type=document.guide_type.value,
            category_slug=document.category_slug,
            limit=3,
        )
        warnings.extend(problems)
        for candidate in results:
            if candidate.remote_url in seen:
                continue
            seen.add(candidate.remote_url)
            if item.subject and not candidate.subject:
                candidate = candidate.model_copy(update={"subject": item.subject})
            queries[candidate.remote_url] = item.query
            picked.append((candidate, item.role))
            break
    return picked, warnings, queries


def queue_generation_job(
    db: Session,
    *,
    topic: str,
    guide_type: GuideType | None,
    entry_type: EntryType | None,
    category_slug: str | None,
    instructions: str | None,
    attach_images: bool,
    user: User,
    guide_id: uuid.UUID | None = None,
    replace_images: bool = False,
) -> ResearchJob:
    job = ResearchJob(
        topic=topic.strip(),
        normalized_topic=normalize_text(topic),
        guide_type=guide_type,
        instructions=instructions,
        provider_config={
            "entry_type": entry_type.value if entry_type else None,
            "category_slug": category_slug,
            "attach_images": attach_images,
            "replace_images": replace_images,
            # Set when rewriting an existing guide, so the result cannot land
            # somewhere else because the model chose a different slug.
            "guide_id": str(guide_id) if guide_id else None,
            "model": settings.openai_model,
        },
        requested_by_user_id=user.id,
    )
    db.add(job)
    db.flush()
    add_audit_log(db, user, "research_job.queued", "research_job", job.id, {"topic": job.topic})
    db.commit()
    db.refresh(job)
    return job


def run_generation_job(
    db: Session,
    job_id: uuid.UUID,
    *,
    complete: ai.CompletionFn | None = None,
) -> ResearchJob:
    """Claim one queued job, generate, and leave a draft guide behind.

    Failures are recorded on the job rather than raised: the admin panel polls this
    row, and a failed job with a readable message is more useful than a 500.
    """
    job = db.scalar(select(ResearchJob).where(ResearchJob.id == job_id).with_for_update())
    if job is None:
        raise LookupError("Research job not found")
    if job.status not in {ResearchJobStatus.QUEUED, ResearchJobStatus.RUNNING}:
        return job

    author = db.get(User, job.requested_by_user_id) if job.requested_by_user_id else None
    if author is None:
        job.status = ResearchJobStatus.FAILED
        job.error_message = "The requesting account no longer exists"
        job.finished_at = datetime.now(UTC)
        db.commit()
        return job

    job.status = ResearchJobStatus.RUNNING
    job.started_at = datetime.now(UTC)
    job.attempt_count += 1
    job.error_message = None
    db.commit()

    config = job.provider_config or {}
    warnings: list[str] = []
    try:
        result = ai.generate_guide_document(
            job.topic,
            category_slugs=active_category_slugs(db),
            guide_type=job.guide_type,
            entry_type=EntryType(config["entry_type"]) if config.get("entry_type") else None,
            instructions=job.instructions,
            complete=complete,
        )
        document = result.document
        if settings.ai_verify_sources:
            document, source_warnings = ai.verify_sources(document)
            warnings.extend(source_warnings)

        forced_category = config.get("category_slug")
        if forced_category:
            document = document.model_copy(update={"category_slug": slugify(forced_category)})

        target_id = config.get("guide_id")
        if target_id:
            target = db.get(Guide, uuid.UUID(target_id))
            if target is None:
                raise LookupError("The guide being regenerated no longer exists")
            # A slug is permanent, and save_draft rejects a change, so pin it.
            document = document.model_copy(update={"slug": target.slug})

        guide, revision = store_document_as_draft(db, document, author)

        if config.get("replace_images"):
            for link in db.scalars(
                select(GuideMedia).where(GuideMedia.guide_revision_id == revision.id)
            ).all():
                db.delete(link)
            db.flush()

        existing_media = db.scalar(
            select(func.count())
            .select_from(GuideMedia)
            .where(GuideMedia.guide_revision_id == revision.id)
        ) or 0

        attached: list[dict] = []
        if config.get("attach_images", True) and not existing_media:
            picked, image_warnings, queries = fetch_planned_images(document)
            warnings.extend(image_warnings)
            for asset, link in attach_images(db, revision, picked, author, queries=queries):
                attached.append(
                    {
                        "media_asset_id": str(asset.id),
                        "link_id": str(link.id),
                        "provider": asset.provider,
                        "subject": link.caption,
                    }
                )
            if not picked:
                warnings.append("No images were attached; every provider came back empty.")
        elif existing_media:
            warnings.append(
                f"Kept the {existing_media} image(s) already on this draft. "
                "Tick 'replace images' to fetch new ones."
            )

        job.status = ResearchJobStatus.REVIEW
        job.created_guide_id = guide.id
        job.result = {
            "guide_id": str(guide.id),
            "guide_slug": guide.slug,
            "revision_id": str(revision.id),
            "revision_number": revision.revision_number,
            "attempts": result.attempts,
            "input_tokens": result.input_tokens,
            "output_tokens": result.output_tokens,
            "attached_media": attached,
            "warnings": warnings,
        }
        job.estimated_cost_micros = result.estimated_cost_micros
        job.finished_at = datetime.now(UTC)
        add_audit_log(
            db,
            author,
            "research_job.generated",
            "research_job",
            job.id,
            {"guide_id": str(guide.id), "warnings": warnings},
        )
        db.commit()
    except Exception as exc:  # noqa: BLE001 - the message belongs on the job row
        db.rollback()
        failed = db.get(ResearchJob, job_id)
        if failed is not None:
            failed.status = ResearchJobStatus.FAILED
            failed.error_message = f"{type(exc).__name__}: {exc}"[:5000]
            failed.finished_at = datetime.now(UTC)
            db.commit()
            db.refresh(failed)
            return failed
        raise

    db.refresh(job)
    return job
