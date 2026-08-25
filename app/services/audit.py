import uuid
from typing import Any

from sqlalchemy.orm import Session

from app.db.models import AuditLog, User


def add_audit_log(
    db: Session,
    actor: User | None,
    action: str,
    entity_type: str,
    entity_id: uuid.UUID | str,
    details: dict[str, Any] | None = None,
) -> None:
    db.add(
        AuditLog(
            actor_user_id=actor.id if actor else None,
            action=action,
            entity_type=entity_type,
            entity_id=str(entity_id),
            details=details or {},
        )
    )
