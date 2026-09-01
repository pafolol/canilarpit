import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import delete, func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import get_current_user
from app.db.models import (
    Category,
    Guide,
    GuideHistory,
    GuideStatus,
    SavedGuide,
    SearchHistory,
    User,
)
from app.db.session import get_db
from app.schemas.api import (
    HistoryItem,
    HistoryPage,
    SavedGuideItem,
    SavedGuidePage,
    SearchHistoryCreate,
    SearchHistoryPage,
    SearchHistoryResponse,
    UserResponse,
)
from app.services.guides import guide_list_item, pagination
from app.services.text import normalize_text

# Signed in for the whole prefix. Every route below asks for the user anyway,
# and FastAPI resolves the dependency once, so this costs nothing and closes
# the gap where a new route forgets to ask.
router = APIRouter(
    prefix="/me", tags=["account"], dependencies=[Depends(get_current_user)]
)


def published_guide_or_404(db: Session, guide_id: uuid.UUID) -> Guide:
    guide = db.scalar(
        select(Guide).where(Guide.id == guide_id, Guide.status == GuideStatus.PUBLISHED)
    )
    if guide is None:
        raise HTTPException(status_code=404, detail="Published guide not found")
    return guide


@router.get("", response_model=UserResponse)
def get_me(user: User = Depends(get_current_user)) -> User:
    return user


@router.get("/history", response_model=HistoryPage)
def list_history(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=settings.default_page_size, ge=1, le=settings.max_page_size),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> HistoryPage:
    base = (
        select(GuideHistory.id)
        .join(Guide, Guide.id == GuideHistory.guide_id)
        .where(GuideHistory.user_id == user.id, Guide.status == GuideStatus.PUBLISHED)
    )
    total = db.scalar(select(func.count()).select_from(base.subquery())) or 0
    rows = db.execute(
        select(GuideHistory, Guide, Category)
        .join(Guide, Guide.id == GuideHistory.guide_id)
        .join(Category, Category.id == Guide.category_id)
        .where(GuideHistory.user_id == user.id, Guide.status == GuideStatus.PUBLISHED)
        .order_by(GuideHistory.last_viewed_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()
    return HistoryPage(
        items=[
            HistoryItem(
                guide=guide_list_item(db, guide, category),
                first_viewed_at=history.first_viewed_at,
                last_viewed_at=history.last_viewed_at,
                view_count=history.view_count,
            )
            for history, guide, category in rows
        ],
        pagination=pagination(page, page_size, total),
    )


@router.put("/history/{guide_id}", response_model=HistoryItem)
def record_guide_view(
    guide_id: uuid.UUID,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> HistoryItem:
    guide = published_guide_or_404(db, guide_id)
    statement = (
        pg_insert(GuideHistory)
        .values(user_id=user.id, guide_id=guide.id, view_count=1)
        .on_conflict_do_update(
            index_elements=[GuideHistory.user_id, GuideHistory.guide_id],
            set_={
                "last_viewed_at": func.now(),
                "view_count": GuideHistory.view_count + 1,
            },
        )
        .returning(GuideHistory)
    )
    history = db.execute(statement).scalar_one()
    db.commit()
    return HistoryItem(
        guide=guide_list_item(db, guide),
        first_viewed_at=history.first_viewed_at,
        last_viewed_at=history.last_viewed_at,
        view_count=history.view_count,
    )


@router.delete("/history/{guide_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_history_item(
    guide_id: uuid.UUID,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Response:
    db.execute(
        delete(GuideHistory).where(
            GuideHistory.user_id == user.id, GuideHistory.guide_id == guide_id
        )
    )
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.delete("/history", status_code=status.HTTP_204_NO_CONTENT)
def clear_history(
    db: Session = Depends(get_db), user: User = Depends(get_current_user)
) -> Response:
    db.execute(delete(GuideHistory).where(GuideHistory.user_id == user.id))
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/saved", response_model=SavedGuidePage)
def list_saved_guides(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=settings.default_page_size, ge=1, le=settings.max_page_size),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> SavedGuidePage:
    total = (
        db.scalar(
            select(func.count())
            .select_from(SavedGuide)
            .join(Guide, Guide.id == SavedGuide.guide_id)
            .where(SavedGuide.user_id == user.id, Guide.status == GuideStatus.PUBLISHED)
        )
        or 0
    )
    rows = db.execute(
        select(SavedGuide, Guide, Category)
        .join(Guide, Guide.id == SavedGuide.guide_id)
        .join(Category, Category.id == Guide.category_id)
        .where(SavedGuide.user_id == user.id, Guide.status == GuideStatus.PUBLISHED)
        .order_by(SavedGuide.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()
    return SavedGuidePage(
        items=[
            SavedGuideItem(guide=guide_list_item(db, guide, category), saved_at=saved.created_at)
            for saved, guide, category in rows
        ],
        pagination=pagination(page, page_size, total),
    )


@router.put("/saved/{guide_id}", response_model=SavedGuideItem)
def save_guide(
    guide_id: uuid.UUID,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> SavedGuideItem:
    guide = published_guide_or_404(db, guide_id)
    statement = (
        pg_insert(SavedGuide)
        .values(user_id=user.id, guide_id=guide.id)
        .on_conflict_do_nothing(index_elements=[SavedGuide.user_id, SavedGuide.guide_id])
        .returning(SavedGuide)
    )
    saved = db.execute(statement).scalar_one_or_none()
    if saved is None:
        saved = db.scalar(
            select(SavedGuide).where(SavedGuide.user_id == user.id, SavedGuide.guide_id == guide.id)
        )
    if saved is None:
        raise HTTPException(status_code=500, detail="Saved guide upsert failed")
    db.commit()
    return SavedGuideItem(guide=guide_list_item(db, guide), saved_at=saved.created_at)


@router.delete("/saved/{guide_id}", status_code=status.HTTP_204_NO_CONTENT)
def unsave_guide(
    guide_id: uuid.UUID,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Response:
    db.execute(
        delete(SavedGuide).where(SavedGuide.user_id == user.id, SavedGuide.guide_id == guide_id)
    )
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/search-history", response_model=SearchHistoryPage)
def list_search_history(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=settings.default_page_size, ge=1, le=settings.max_page_size),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> SearchHistoryPage:
    total = (
        db.scalar(
            select(func.count()).select_from(SearchHistory).where(SearchHistory.user_id == user.id)
        )
        or 0
    )
    items = db.scalars(
        select(SearchHistory)
        .where(SearchHistory.user_id == user.id)
        .order_by(SearchHistory.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()
    return SearchHistoryPage(
        items=[
            SearchHistoryResponse(
                id=item.id,
                query=item.query,
                matched_guide_id=item.matched_guide_id,
                created_at=item.created_at,
            )
            for item in items
        ],
        pagination=pagination(page, page_size, total),
    )


@router.post("/search-history", response_model=SearchHistoryResponse, status_code=201)
def record_search(
    payload: SearchHistoryCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> SearchHistory:
    if payload.matched_guide_id:
        published_guide_or_404(db, payload.matched_guide_id)
    history = SearchHistory(
        user_id=user.id,
        query=payload.query.strip(),
        normalized_query=normalize_text(payload.query),
        matched_guide_id=payload.matched_guide_id,
    )
    db.add(history)
    db.commit()
    db.refresh(history)
    return history


@router.delete("/search-history", status_code=status.HTTP_204_NO_CONTENT)
def clear_search_history(
    db: Session = Depends(get_db), user: User = Depends(get_current_user)
) -> Response:
    db.execute(delete(SearchHistory).where(SearchHistory.user_id == user.id))
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
