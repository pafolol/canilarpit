"""Who is asking, verified on every single request.

There is no trusted network here and nothing the server takes on faith. A
request carries a session cookie or it carries nothing, and what it is allowed
to do is read out of the database at the moment it asks - never from the cookie,
never from a cache, never from a previous request. An editor demoted a second
ago is demoted on their next call.

The cookie is an opaque random string, not a signed token. That distinction is
the whole design: a signed token is valid until it expires and there is nowhere
to go to say otherwise, whereas a session is a row, and a row can be marked
revoked and refused on the very next request. Signing out actually signs out.

The checks, in the order they run:

  1. The client's recent failures, before any lookup, so grinding costs the
     grinder rather than the server.
  2. The session: exists, not revoked, not expired.
  3. The CSRF pair, on anything that can change something. A form on another
     site can make a browser send our cookie; it cannot read the cookie, so it
     cannot produce the matching header.
  4. The account: active, not soft-deleted, and holding the role this route
     wants.

The development bypass is refused twice: the settings validator will not build
a production configuration with it on, and `dev_identity_allowed` re-reads the
environment at request time anyway. One of those is the belt.
"""

import logging

from fastapi import Depends, Header, HTTPException, Request, status
from fastapi.security import APIKeyCookie
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session as DbSession

from app.core.auth_guard import guard_auth_attempts, record_auth_success
from app.core.config import settings
from app.db.models import Session, User, UserRole
from app.db.session import get_db
from app.services import sessions as session_service

logger = logging.getLogger(__name__)

UNAUTHENTICATED = {"WWW-Authenticate": "Cookie"}

# Declared so the schema says how to authenticate, and so a route that needs a
# session is marked as such. It never raises on its own - the checks below do.
session_scheme = APIKeyCookie(
    name=session_service.SESSION_COOKIE, scheme_name="SessionCookie", auto_error=False
)


def unauthorized(detail: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED, detail=detail, headers=UNAUTHENTICATED
    )


def dev_identity_allowed() -> bool:
    """The bypass, re-decided per request instead of trusted from boot.

    `prevent_production_auth_bypass` already refuses to build these settings in
    production. This is the second lock on the same door: whatever the settings
    object says, a production process does not accept an identity header.
    """
    return settings.dev_auth_bypass and not settings.is_production


def user_for_external_id(db: DbSession, external_id: str, email: str | None, name: str | None):
    """Find or create a non-password identity. Development and seeding only."""
    inserted_id = db.execute(
        pg_insert(User)
        .values(external_id=external_id, email=email, display_name=name)
        .on_conflict_do_nothing(index_elements=[User.external_id])
        .returning(User.id)
    ).scalar_one_or_none()
    user = (
        db.get(User, inserted_id)
        if inserted_id
        else db.scalar(select(User).where(User.external_id == external_id))
    )
    if user is None:
        db.rollback()
        raise HTTPException(status_code=500, detail="Unable to synchronize the development user")
    db.commit()
    return user


def current_session(request: Request, db: DbSession) -> Session | None:
    """The session this request's cookie names, if it is still one."""
    token = request.cookies.get(session_service.SESSION_COOKIE)
    if not token:
        return None

    client = guard_auth_attempts(request)
    session = session_service.active_session(db, token)
    if session is None:
        # A cookie that names nothing is either stale or somebody trying. Both
        # count, and neither is told which it was.
        logger.warning(
            "Rejected a session cookie on %s %s: unknown, revoked or expired.",
            request.method,
            request.url.path,
        )
        return None

    record_auth_success(client)
    session_service.touch(db, session)
    db.commit()
    return session


def get_optional_user(
    request: Request,
    db: DbSession = Depends(get_db),
    _scheme: str | None = Depends(session_scheme),
    x_dev_user: str | None = Header(default=None),
    x_dev_email: str | None = Header(default=None),
) -> User | None:
    session = current_session(request, db)
    if session is not None:
        # Only now, and only for a method that can change something. A GET that
        # fails a CSRF check would be a bug rather than an attack.
        if not session_service.csrf_ok(request):
            logger.warning(
                "CSRF check failed on %s %s (cookie %s, header %s)",
                request.method,
                request.url.path,
                "present" if request.cookies.get(session_service.CSRF_COOKIE) else "absent",
                "present" if request.headers.get(session_service.CSRF_HEADER) else "absent",
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="This request is missing its CSRF token. Reload the panel and retry.",
            )
        return db.get(User, session.user_id)

    if x_dev_user:
        if not dev_identity_allowed():
            logger.warning(
                "Ignoring a development identity header on %s %s; the bypass is off.",
                request.method,
                request.url.path,
            )
            return None
        return user_for_external_id(
            db, x_dev_user, x_dev_email, request.headers.get("X-Dev-Display-Name")
        )
    return None


def get_current_user(
    request: Request, user: User | None = Depends(get_optional_user)
) -> User:
    if user is None:
        # "Authentication required" on its own cannot tell an operator whether
        # the browser sent nothing or sent something that was thrown out.
        logger.warning(
            "Unauthenticated %s %s (session cookie %s)",
            request.method,
            request.url.path,
            "present" if request.cookies.get(session_service.SESSION_COOKIE) else "ABSENT",
        )
        raise unauthorized("Authentication required")
    if not user.is_active or user.deleted_at is not None:
        raise HTTPException(status_code=403, detail="Account is inactive")
    return user


def require_editor(user: User = Depends(get_current_user)) -> User:
    if user.role not in {UserRole.EDITOR, UserRole.ADMIN}:
        raise HTTPException(status_code=403, detail="Editor role required")
    return user


def require_admin(user: User = Depends(get_current_user)) -> User:
    if user.role != UserRole.ADMIN:
        raise HTTPException(status_code=403, detail="Administrator role required")
    return user
