"""Signed-in sessions, and the cookies that carry them.

The session token is opaque: 32 random bytes, meaning nothing, decodable into
nothing. It is not a JWT, and that is the point - a JWT is valid until it
expires and there is nowhere to go to say otherwise, whereas a row can be marked
revoked and is refused on the next request. "Sign out everywhere" is a real
operation here rather than a wait.

The database stores only the token's SHA-256. Lookup is by that hash, which is
exact, so unlike a password there is nothing to slow down: the token has 256
bits of entropy and is not guessable at any rate.

Two cookies leave together:

  - `canilarpit_session`, HttpOnly, which JavaScript cannot read and an XSS
    therefore cannot steal.
  - `canilarpit_csrf`, deliberately readable, holding a value the panel must
    echo back in a header on every unsafe request. A form on another site can
    make a browser send our cookies, but it cannot read them and so cannot set
    the matching header. Both halves have to agree, and only our own origin can
    see both.
"""

import hashlib
import secrets
from datetime import UTC, datetime, timedelta

from fastapi import Request, Response
from sqlalchemy import select, update
from sqlalchemy.orm import Session as DbSession

from app.core.antiabuse import client_hash
from app.core.config import settings
from app.db.models import Session, User

SESSION_COOKIE = "canilarpit_session"
CSRF_COOKIE = "canilarpit_csrf"
CSRF_HEADER = "X-CSRF-Token"

# Methods that cannot change anything, and so do not need the CSRF pair.
SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS", "TRACE"})


def token_digest(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def issue_session(db: DbSession, user: User, request: Request) -> tuple[Session, str, str]:
    """Create a session row and return it with the two secrets it needs."""
    token = secrets.token_urlsafe(32)
    csrf = secrets.token_urlsafe(32)
    session = Session(
        user_id=user.id,
        token_hash=token_digest(token),
        expires_at=datetime.now(UTC) + timedelta(seconds=settings.session_lifetime_seconds),
        last_seen_at=datetime.now(UTC),
        user_agent=(request.headers.get("user-agent") or "")[:400] or None,
        client_hash=client_hash(request),
    )
    db.add(session)
    db.flush()
    return session, token, csrf


def active_session(db: DbSession, token: str) -> Session | None:
    """The session this token names, if it is still one."""
    session = db.scalar(select(Session).where(Session.token_hash == token_digest(token)))
    if session is None or session.revoked_at is not None:
        return None
    if session.expires_at <= datetime.now(UTC):
        return None
    return session


def touch(db: DbSession, session: Session) -> None:
    """Record use, but not on every single request.

    A write per request would turn every read of the panel into a write against
    the same row. A minute's granularity is plenty for "last seen".
    """
    now = datetime.now(UTC)
    if (now - session.last_seen_at).total_seconds() > 60:
        session.last_seen_at = now


def revoke(db: DbSession, session: Session) -> None:
    if session.revoked_at is None:
        session.revoked_at = datetime.now(UTC)


def revoke_all_for_user(db: DbSession, user: User, *, except_id: object = None) -> int:
    """Sign out everywhere. Used on a password change, and on request."""
    conditions = [Session.user_id == user.id, Session.revoked_at.is_(None)]
    if except_id is not None:
        conditions.append(Session.id != except_id)
    result = db.execute(
        update(Session).where(*conditions).values(revoked_at=datetime.now(UTC))
    )
    return result.rowcount or 0


# ------------------------------------------------------------------- cookies


def cookie_kwargs() -> dict:
    """Shared flags. `Secure` follows the environment, because a Secure cookie
    is simply not sent over the plain http a laptop develops on."""
    return {
        "path": "/",
        "secure": settings.is_production,
        "samesite": "lax",
        "max_age": settings.session_lifetime_seconds,
    }


def attach(response: Response, token: str, csrf: str) -> None:
    response.set_cookie(SESSION_COOKIE, token, httponly=True, **cookie_kwargs())
    # Readable on purpose: the panel has to echo it back in a header.
    response.set_cookie(CSRF_COOKIE, csrf, httponly=False, **cookie_kwargs())


def clear(response: Response) -> None:
    for name in (SESSION_COOKIE, CSRF_COOKIE):
        response.delete_cookie(name, path="/", samesite="lax", secure=settings.is_production)


def csrf_ok(request: Request) -> bool:
    """Double submit: the readable cookie and the header must agree.

    Another origin can cause the cookie to be sent but cannot read it, so it
    cannot produce the header. Same-origin script can do both, which is exactly
    the code allowed to.
    """
    if request.method in SAFE_METHODS:
        return True
    from app.services.passwords import constant_time_equals

    cookie = request.cookies.get(CSRF_COOKIE)
    header = request.headers.get(CSRF_HEADER)
    return bool(cookie and header and constant_time_equals(cookie, header))


def prune_expired(db: DbSession) -> int:
    """Delete sessions that expired a while ago. Called by the CLI, not per request."""
    cutoff = datetime.now(UTC) - timedelta(days=30)
    result = db.execute(
        Session.__table__.delete().where(Session.expires_at < cutoff)
    )
    return result.rowcount or 0
