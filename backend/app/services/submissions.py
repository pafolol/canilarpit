"""Reader submissions: taking them in, and turning an accepted one into a draft.

Two separate jobs with a deliberate gap between them. Anyone can file a
submission and it costs nothing but a row. An editor decides when a model looks
at one, because that is where the money is, and no unauthenticated request
should be able to spend it.
"""

import uuid
from datetime import UTC, datetime

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import (
    BlockedClient,
    Category,
    EntryType,
    Guide,
    GuideStatus,
    GuideType,
    Submission,
    SubmissionStatus,
    User,
)
from app.services import ai
from app.services.generation import attach_images, fetch_planned_images, store_document_as_draft
from app.services.text import normalize_text, slugify

OPEN_STATES = (SubmissionStatus.PENDING, SubmissionStatus.SCREENED, SubmissionStatus.DRAFTED)


def assert_not_blocked(db: Session, client: str) -> None:
    blocked = db.scalar(select(BlockedClient.id).where(BlockedClient.client_hash == client))
    if blocked:
        # Same wording as a rate limit: a blocked client learns nothing from it.
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="You have sent enough for now. Try again later.",
        )


def assert_within_quota(db: Session, client: str, max_pending: int) -> None:
    """A database quota, so a restart does not hand somebody a fresh allowance."""
    pending = db.scalar(
        select(func.count())
        .select_from(Submission)
        .where(Submission.client_hash == client, Submission.status.in_(OPEN_STATES))
    )
    if (pending or 0) >= max_pending:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=(
                f"You already have {pending} suggestions waiting. "
                "Let an editor read those first."
            ),
        )


def existing_guide_for(db: Session, topic: str) -> Guide | None:
    normalized = normalize_text(topic)
    return db.scalar(
        select(Guide).where(
            Guide.status == GuideStatus.PUBLISHED,
            Guide.slug == normalized.replace(" ", "-"),
        )
    )


def assert_not_duplicate(db: Session, client: str, topic: str) -> None:
    normalized = normalize_text(topic)
    already = db.scalar(
        select(Submission.id).where(
            Submission.client_hash == client,
            Submission.normalized_topic == normalized,
            Submission.status.in_(OPEN_STATES),
        )
    )
    if already:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="You have already suggested this one. It is in the queue.",
        )


def create_submission(
    db: Session,
    *,
    client: str,
    topic: str,
    notes: str,
    guide_type: GuideType | None,
    entry_type: EntryType | None,
    category_slug: str | None,
    suggested_category: str | None,
    credit_name: str | None,
) -> Submission:
    category = None
    if category_slug:
        category = db.scalar(
            select(Category).where(Category.slug == category_slug, Category.is_active.is_(True))
        )
        if category is None:
            raise HTTPException(status_code=422, detail=f"Unknown category: {category_slug}")

    submission = Submission(
        topic=" ".join(topic.split()),
        normalized_topic=normalize_text(topic),
        notes=notes.strip(),
        guide_type=guide_type,
        entry_type=entry_type,
        category_id=category.id if category else None,
        # Stored as typed, promoted to a real category only by an editor.
        suggested_category=" ".join(suggested_category.split()) if suggested_category else None,
        credit_name=" ".join(credit_name.split()) if credit_name else None,
        client_hash=client,
    )
    db.add(submission)
    db.commit()
    db.refresh(submission)
    return submission


def active_category_slugs(db: Session) -> list[str]:
    return list(
        db.scalars(
            select(Category.slug)
            .where(Category.is_active.is_(True))
            .order_by(Category.sort_order, Category.slug)
        ).all()
    )


def review_submission(
    db: Session,
    submission: Submission,
    editor: User,
    *,
    generate: bool = True,
    complete: ai.CompletionFn | None = None,
) -> Submission:
    """Screen it, and write the draft when it passes.

    Everything the model returns is advisory. The submission never publishes
    itself: the most it reaches is a draft guide with an editor's name on the
    review, and `accept_submission` is a separate, deliberate step.
    """
    categories = active_category_slugs(db)
    screening = ai.screen_submission(
        submission.topic,
        submission.notes,
        category_slugs=categories,
        credit=submission.credit_name,
        complete=complete,
    )
    submission.screening = screening
    submission.reviewed_by_user_id = editor.id
    submission.reviewed_at = datetime.now(UTC)

    verdict = screening.get("verdict")
    if verdict == "spam":
        submission.status = SubmissionStatus.SPAM
        db.commit()
        db.refresh(submission)
        return submission
    if verdict == "reject":
        submission.status = SubmissionStatus.REJECTED
        db.commit()
        db.refresh(submission)
        return submission

    submission.status = SubmissionStatus.SCREENED
    if not generate:
        db.commit()
        db.refresh(submission)
        return submission

    chosen = db.get(Category, submission.category_id) if submission.category_id else None
    proposed = screening.get("category_slug")
    category_slug = chosen.slug if chosen else (proposed if proposed in categories else None)

    result = ai.generate_guide_document(
        submission.topic,
        category_slugs=categories,
        guide_type=submission.guide_type or _as_guide_type(screening.get("guide_type")),
        entry_type=submission.entry_type or _as_entry_type(screening.get("entry_type")),
        instructions=_instructions_from(submission),
        complete=complete,
    )
    document = result.document
    if category_slug:
        document = document.model_copy(update={"category_slug": slugify(category_slug)})

    guide, revision = store_document_as_draft(db, document, editor)
    # The reader who asked for it gets their name on it.
    guide.credit_name = submission.credit_name

    picked, warnings, queries = fetch_planned_images(document)
    attach_images(db, revision, picked, editor, queries=queries)

    submission.status = SubmissionStatus.DRAFTED
    submission.created_guide_id = guide.id
    submission.screening = {
        **screening,
        "generation": {
            "attempts": result.attempts,
            "input_tokens": result.input_tokens,
            "output_tokens": result.output_tokens,
            "images": len(picked),
            "warnings": warnings,
        },
    }
    db.commit()
    db.refresh(submission)
    return submission


def _instructions_from(submission: Submission) -> str:
    """The sender's own note, framed as what it is: a lead, not a specification."""
    lines = [
        "A reader suggested this topic. Their note follows. Treat it as a lead:",
        "use what is accurate, ignore what is not, and do not repeat it verbatim.",
        "",
        submission.notes,
    ]
    if submission.suggested_category:
        lines.append(f"\nThey suggested the category: {submission.suggested_category}")
    return "\n".join(lines)


def _as_guide_type(value: object) -> GuideType | None:
    try:
        return GuideType(value) if value else None
    except ValueError:
        return None


def _as_entry_type(value: object) -> EntryType | None:
    try:
        return EntryType(value) if value else None
    except ValueError:
        return None


def set_status(
    db: Session,
    submission: Submission,
    new_status: SubmissionStatus,
    editor: User,
    notes: str | None = None,
) -> Submission:
    submission.status = new_status
    submission.reviewed_by_user_id = editor.id
    submission.reviewed_at = datetime.now(UTC)
    if notes is not None:
        submission.review_notes = notes
    db.commit()
    db.refresh(submission)
    return submission


def block_client(db: Session, client_hash: str, editor: User, reason: str | None) -> None:
    if db.scalar(select(BlockedClient.id).where(BlockedClient.client_hash == client_hash)):
        return
    db.add(
        BlockedClient(client_hash=client_hash, reason=reason, blocked_by_user_id=editor.id)
    )
    db.commit()


def promote_category(
    db: Session, name: str, editor: User, description: str = "", sort_order: int = 500
) -> Category:
    """Turn a suggested category into a real one."""
    slug = slugify(name)
    existing = db.scalar(select(Category).where(Category.slug == slug))
    if existing is not None:
        existing.is_active = True
        db.commit()
        db.refresh(existing)
        return existing

    category = Category(
        slug=slug,
        title=" ".join(name.split()).title(),
        description=description,
        sort_order=sort_order,
    )
    db.add(category)
    db.commit()
    db.refresh(category)
    return category


def submission_or_404(db: Session, submission_id: uuid.UUID) -> Submission:
    submission = db.get(Submission, submission_id)
    if submission is None:
        raise HTTPException(status_code=404, detail="Submission not found")
    return submission
