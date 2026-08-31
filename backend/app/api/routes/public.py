from typing import Literal

from fastapi import APIRouter, Depends, Query, Request, Response, status
from sqlalchemy import case, exists, func, or_, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.core import antiabuse
from app.core.config import settings
from app.core.rate_limit import limiter
from app.db.models import (
    Category,
    EntryType,
    Guide,
    GuideAlias,
    GuideStatus,
    GuideType,
    TopicRequest,
    Verdict,
)
from app.db.session import get_db
from app.schemas.api import (
    CategoryResponse,
    GuideDetail,
    GuideListItem,
    GuidePage,
    SiteConfigResponse,
    SubmissionCreate,
    SubmissionFormToken,
    SubmissionReceipt,
    TopicRequestCreate,
    TopicRequestResponse,
)
from app.services import submissions as submission_service
from app.services.guides import (
    guide_detail,
    guide_list_item,
    pagination,
    published_guide_by_slug,
)
from app.services.text import normalize_text

router = APIRouter(tags=["public catalog"])


@router.get("/config", response_model=SiteConfigResponse)
def site_config() -> SiteConfigResponse:
    """Which sign-in paths the admin panel should offer. No secrets are returned."""
    return SiteConfigResponse(
        app_env=settings.app_env,
        dev_auth_bypass=settings.dev_auth_bypass,
        clerk_configured=bool(settings.clerk_issuer and settings.clerk_jwks_url),
    )


@router.get("/categories", response_model=list[CategoryResponse])
def list_categories(db: Session = Depends(get_db)) -> list[CategoryResponse]:
    rows = db.execute(
        select(Category, func.count(Guide.id))
        .outerjoin(
            Guide,
            (Guide.category_id == Category.id) & (Guide.status == GuideStatus.PUBLISHED),
        )
        .where(Category.is_active.is_(True))
        .group_by(Category.id)
        .order_by(Category.sort_order, Category.title)
    ).all()
    return [
        CategoryResponse(
            id=category.id,
            slug=category.slug,
            title=category.title,
            description=category.description,
            sort_order=category.sort_order,
            published_guide_count=count,
        )
        for category, count in rows
    ]


@router.get("/guides", response_model=GuidePage)
def list_guides(
    q: str | None = Query(default=None, min_length=1, max_length=200),
    category: str | None = Query(default=None, max_length=80),
    guide_type: GuideType | None = None,
    entry_type: list[EntryType] | None = Query(default=None),
    verdict: list[Verdict] | None = Query(default=None),
    sort: Literal["relevance", "newest", "title"] = "relevance",
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=settings.default_page_size, ge=1, le=settings.max_page_size),
    db: Session = Depends(get_db),
) -> GuidePage:
    query = (
        select(Guide, Category)
        .join(Category, Category.id == Guide.category_id)
        .where(Guide.status == GuideStatus.PUBLISHED)
    )
    if category:
        query = query.where(Category.slug == category)
    if guide_type:
        query = query.where(Guide.guide_type == guide_type)
    # Repeated values within a group widen the result; separate groups intersect.
    if entry_type:
        query = query.where(Guide.entry_type.in_(entry_type))
    if verdict:
        query = query.where(Guide.verdict.in_(verdict))

    relevance_order = None
    if q:
        normalized = normalize_text(q)
        alias_match = exists(
            select(GuideAlias.id).where(
                GuideAlias.guide_id == Guide.id,
                or_(
                    GuideAlias.normalized_alias == normalized,
                    GuideAlias.normalized_alias.ilike(f"%{normalized}%"),
                ),
            )
        )
        query = query.where(
            or_(
                func.lower(Guide.title) == q.lower(),
                Guide.title.ilike(f"%{q}%"),
                Guide.summary.ilike(f"%{q}%"),
                func.similarity(Guide.title, q) > 0.2,
                alias_match,
            )
        )
        relevance_order = (
            case((func.lower(Guide.title) == q.lower(), 3), (alias_match, 2), else_=1).desc(),
            func.similarity(Guide.title, q).desc(),
        )

    total = db.scalar(select(func.count()).select_from(query.order_by(None).subquery())) or 0
    if sort == "title":
        query = query.order_by(Guide.title)
    elif sort == "newest" or not q:
        query = query.order_by(Guide.published_at.desc(), Guide.title)
    elif relevance_order:
        query = query.order_by(*relevance_order, Guide.title)

    rows = db.execute(query.offset((page - 1) * page_size).limit(page_size)).all()
    return GuidePage(
        items=[guide_list_item(db, guide, item_category) for guide, item_category in rows],
        pagination=pagination(page, page_size, total),
    )


@router.get("/guides/{slug}", response_model=GuideDetail)
def get_guide(slug: str, db: Session = Depends(get_db)) -> GuideDetail:
    return guide_detail(db, published_guide_by_slug(db, slug))


@router.get("/guides/{slug}/related", response_model=list[GuideListItem])
def related_guides(
    slug: str,
    limit: int = Query(default=6, ge=1, le=20),
    db: Session = Depends(get_db),
) -> list[GuideListItem]:
    guide = published_guide_by_slug(db, slug)
    rows = db.execute(
        select(Guide, Category)
        .join(Category, Category.id == Guide.category_id)
        .where(
            Guide.status == GuideStatus.PUBLISHED,
            Guide.category_id == guide.category_id,
            Guide.id != guide.id,
        )
        .order_by(Guide.published_at.desc(), Guide.title)
        .limit(limit)
    ).all()
    return [guide_list_item(db, item, category) for item, category in rows]


@router.post("/topic-requests", response_model=TopicRequestResponse)
@limiter.limit("10/minute")
def request_topic(
    request: Request,
    payload: TopicRequestCreate,
    db: Session = Depends(get_db),
) -> TopicRequestResponse:
    normalized = normalize_text(payload.topic)
    alias_guide_id = db.scalar(
        select(GuideAlias.guide_id)
        .join(Guide, Guide.id == GuideAlias.guide_id)
        .where(
            GuideAlias.normalized_alias == normalized,
            Guide.status == GuideStatus.PUBLISHED,
        )
        .limit(1)
    )
    matching_guide = db.scalar(
        select(Guide).where(
            Guide.status == GuideStatus.PUBLISHED,
            or_(
                Guide.slug == normalized.replace(" ", "-"),
                func.lower(Guide.title) == payload.topic.lower(),
                Guide.id == alias_guide_id,
            ),
        )
    )
    if matching_guide:
        return TopicRequestResponse(
            topic=payload.topic,
            normalized_topic=normalized,
            recorded=False,
            matching_guide=guide_list_item(db, matching_guide),
        )

    statement = (
        pg_insert(TopicRequest)
        .values(
            topic=payload.topic.strip(),
            normalized_topic=normalized,
            request_count=1,
            last_requested_by_user_id=None,
        )
        .on_conflict_do_update(
            index_elements=[TopicRequest.normalized_topic],
            set_={
                "topic": payload.topic.strip(),
                "request_count": TopicRequest.request_count + 1,
                "last_requested_at": func.now(),
                "last_requested_by_user_id": None,
            },
        )
        .returning(TopicRequest)
    )
    topic_request = db.execute(statement).scalar_one()
    db.commit()
    return TopicRequestResponse(
        topic=topic_request.topic,
        normalized_topic=topic_request.normalized_topic,
        request_count=topic_request.request_count,
        recorded=True,
    )


@router.get("/submissions/form", response_model=SubmissionFormToken)
@limiter.limit("30/hour", key_func=antiabuse.client_hash)
def submission_form(request: Request) -> SubmissionFormToken:
    """Open the form.

    The token is bound to this client and this moment, so a submission has to
    have come from a form somebody actually opened, recently, from here.
    """
    token = antiabuse.issue_form_token(antiabuse.client_hash(request))
    return SubmissionFormToken(
        token=token.value,
        min_seconds=settings.submission_min_seconds,
        expires_in=settings.submission_token_ttl_seconds,
    )


@router.post("/submissions", response_model=SubmissionReceipt)
# Keyed on the client fingerprint, not the address. Behind a proxy every visitor
# shares one address, so an address-keyed limit would let one person shut the
# form for everybody.
@limiter.limit(settings.submissions_per_day, key_func=antiabuse.client_hash)
@limiter.limit(settings.submissions_per_hour, key_func=antiabuse.client_hash)
def create_submission(
    request: Request,
    payload: SubmissionCreate,
    response: Response,
    db: Session = Depends(get_db),
) -> SubmissionReceipt:
    """Suggest a guide.

    The only unauthenticated write on the site that stores prose, so it is
    guarded in five independent ways before a row is created, and it never
    spends a penny: an editor decides when a model looks at it.
    """
    client = antiabuse.client_hash(request)

    antiabuse.check_honeypot(payload.website)
    antiabuse.check_form_token(payload.token, client)
    submission_service.assert_not_blocked(db, client)
    antiabuse.check_notes(payload.notes)

    existing = submission_service.existing_guide_for(db, payload.topic)
    if existing is not None:
        return SubmissionReceipt(
            received=False,
            topic=payload.topic,
            message="This one is already written. Have a look and tell us what is missing.",
            matching_guide=guide_list_item(db, existing),
        )

    submission_service.assert_not_duplicate(db, client, payload.topic)
    submission_service.assert_within_quota(db, client, settings.submission_max_pending)

    response.status_code = status.HTTP_201_CREATED
    submission = submission_service.create_submission(
        db,
        client=client,
        topic=payload.topic,
        notes=payload.notes,
        guide_type=payload.guide_type,
        entry_type=payload.entry_type,
        category_slug=payload.category_slug,
        suggested_category=payload.suggested_category,
        credit_name=payload.credit_name,
    )
    credited = (
        f" If it runs, it will say suggested by {submission.credit_name}."
        if submission.credit_name
        else ""
    )
    return SubmissionReceipt(
        received=True,
        topic=submission.topic,
        message=f"Sent. An editor reads every one of these before anything is written.{credited}",
    )
