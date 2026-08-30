from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session
from svix.webhooks import Webhook, WebhookVerificationError

from app.core.config import settings
from app.db.models import User, WebhookEvent
from app.db.session import get_db

router = APIRouter(prefix="/webhooks", tags=["webhooks"])


def primary_email(data: dict) -> str | None:
    primary_id = data.get("primary_email_address_id")
    addresses = data.get("email_addresses") or []
    for address in addresses:
        if address.get("id") == primary_id:
            return address.get("email_address")
    return addresses[0].get("email_address") if addresses else None


def clerk_event_time(data: dict) -> datetime | None:
    raw_timestamp = data.get("updated_at") or data.get("created_at")
    if not isinstance(raw_timestamp, int | float):
        return None
    seconds = raw_timestamp / 1000 if raw_timestamp > 10_000_000_000 else raw_timestamp
    return datetime.fromtimestamp(seconds, tz=UTC)


@router.post("/clerk")
async def clerk_webhook(request: Request, db: Session = Depends(get_db)) -> dict[str, bool]:
    if not settings.clerk_webhook_secret:
        raise HTTPException(status_code=503, detail="Clerk webhook secret is not configured")

    body = await request.body()
    try:
        event = Webhook(settings.clerk_webhook_secret).verify(body, dict(request.headers))
    except WebhookVerificationError as exc:
        raise HTTPException(status_code=400, detail="Invalid Clerk webhook signature") from exc

    event_id = request.headers.get("svix-id")
    event_type = event.get("type", "unknown")
    if not event_id:
        raise HTTPException(status_code=400, detail="Webhook event ID is missing")
    claimed_event_id = db.execute(
        pg_insert(WebhookEvent)
        .values(provider="clerk", external_event_id=event_id, event_type=event_type)
        .on_conflict_do_nothing(
            index_elements=[WebhookEvent.provider, WebhookEvent.external_event_id]
        )
        .returning(WebhookEvent.id)
    ).scalar_one_or_none()
    if claimed_event_id is None:
        db.rollback()
        return {"processed": False}

    data = event.get("data") or {}
    clerk_user_id = data.get("id")
    incoming_updated_at = clerk_event_time(data)
    if clerk_user_id and event_type in {"user.created", "user.updated"}:
        db.execute(
            pg_insert(User)
            .values(clerk_user_id=clerk_user_id)
            .on_conflict_do_nothing(index_elements=[User.clerk_user_id])
        )
        user = db.scalar(select(User).where(User.clerk_user_id == clerk_user_id).with_for_update())
        if user is None:
            raise HTTPException(status_code=500, detail="Unable to synchronize Clerk user")
        is_newer = user.clerk_updated_at is None or (
            incoming_updated_at is not None and incoming_updated_at > user.clerk_updated_at
        )
        if is_newer and not (user.deleted_at is not None and incoming_updated_at is None):
            first_name = data.get("first_name") or ""
            last_name = data.get("last_name") or ""
            user.display_name = " ".join((first_name, last_name)).strip() or data.get("username")
            user.email = primary_email(data)
            user.avatar_url = data.get("image_url")
            user.is_active = True
            user.deleted_at = None
            user.clerk_updated_at = incoming_updated_at or datetime.now(UTC)
    elif clerk_user_id and event_type == "user.deleted":
        deletion_time = incoming_updated_at or datetime.now(UTC)
        db.execute(
            pg_insert(User)
            .values(
                clerk_user_id=clerk_user_id,
                is_active=False,
                deleted_at=deletion_time,
                clerk_updated_at=deletion_time,
            )
            .on_conflict_do_nothing(index_elements=[User.clerk_user_id])
        )
        user = db.scalar(select(User).where(User.clerk_user_id == clerk_user_id).with_for_update())
        is_newer = user is not None and (
            user.clerk_updated_at is None
            or incoming_updated_at is None
            or incoming_updated_at > user.clerk_updated_at
        )
        if user and is_newer:
            user.is_active = False
            user.deleted_at = deletion_time
            user.clerk_updated_at = deletion_time

    db.commit()
    return {"processed": True}
