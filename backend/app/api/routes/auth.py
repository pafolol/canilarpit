"""Signing in, signing out, and changing a password.

The only unauthenticated write in here is `POST /auth/login`, and it is built on
the assumption that somebody is attacking it:

  - Two throttles, one on the caller and one on the account, because moving
    address beats the first and nothing beats the second.
  - A wrong address and a wrong password produce the same message and, because
    a missing account still pays for a full Argon2 verification, roughly the
    same amount of time. Neither answers "does this person have an account".
  - Both throttles are consulted before the account is looked up, so being
    rate-limited does not confirm an address either.

There is no registration endpoint, by design. Accounts are made by an
administrator - `canilarpit create-user` for the first one, the panel's Editors
tab after that - because an admin panel that lets a stranger create an account
is an admin panel with a stranger in it.
"""

import logging

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from app.core.auth_guard import (
    guard_account,
    guard_auth_attempts,
    record_account_success,
    record_auth_success,
)
from app.core.security import get_current_user
from app.db.models import User
from app.db.session import get_db
from app.schemas.api import (
    LoginRequest,
    PasswordChangeRequest,
    SessionItem,
    UserResponse,
)
from app.services import passwords, sessions
from app.services.audit import add_audit_log

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["authentication"])

# One message for every way a sign-in can fail. Which half was wrong is a hint,
# and a hint is worth something to somebody working through a list of addresses.
REFUSED = "That email and password do not match an account."


@router.post("/login", response_model=UserResponse)
def login(
    payload: LoginRequest,
    request: Request,
    response: Response,
    db: DbSession = Depends(get_db),
) -> User:
    email = payload.email.strip().lower()
    # Both before the lookup, so a throttle never confirms an address exists.
    client = guard_auth_attempts(request)
    guard_account(email)

    user = db.scalar(select(User).where(User.email == email))
    if user is None:
        # Spend a verification's worth of time on nothing, so a missing account
        # is not detectable by how fast it is refused.
        passwords.verify_dummy()
        logger.warning("Failed sign-in: no account for that address.")
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=REFUSED)

    if not passwords.verify_password(user.password_hash, payload.password):
        logger.warning("Failed sign-in for user %s: wrong password.", user.id)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=REFUSED)

    if not user.is_active or user.deleted_at is not None:
        # Deliberately the same message: whether an account is disabled is not
        # something an unauthenticated caller needs to learn.
        logger.warning("Failed sign-in for user %s: account is inactive.", user.id)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=REFUSED)

    # The cost settings can be raised later; a hash made under the old ones is
    # rewritten here, the one moment the plaintext is legitimately in hand.
    if user.password_hash and passwords.needs_rehash(user.password_hash):
        user.password_hash = passwords.hash_password(payload.password)

    record_auth_success(client)
    record_account_success(email)

    session, token, csrf = sessions.issue_session(db, user, request)
    add_audit_log(db, user, "auth.signed_in", "session", session.id)
    db.commit()

    sessions.attach(response, token, csrf)
    return user


@router.post("/logout", status_code=204)
def logout(request: Request, response: Response, db: DbSession = Depends(get_db)) -> Response:
    """Ends this browser's session. Safe to call when already signed out."""
    token = request.cookies.get(sessions.SESSION_COOKIE)
    if token:
        session = sessions.active_session(db, token)
        if session is not None:
            sessions.revoke(db, session)
            db.commit()
    sessions.clear(response)
    return Response(status_code=204)


@router.post("/logout-everywhere", status_code=204)
def logout_everywhere(
    response: Response,
    db: DbSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Response:
    """Revokes every session this account has, including this one.

    The thing you reach for when a laptop goes missing. It works because a
    session is a row rather than a signature.
    """
    count = sessions.revoke_all_for_user(db, user)
    add_audit_log(db, user, "auth.revoked_all_sessions", "user", user.id, {"sessions": count})
    db.commit()
    sessions.clear(response)
    return Response(status_code=204)


@router.get("/sessions", response_model=list[SessionItem])
def list_sessions(
    request: Request,
    db: DbSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[SessionItem]:
    """This account's live sessions, so a stranger's is visible as one."""
    token = request.cookies.get(sessions.SESSION_COOKIE) or ""
    this_hash = sessions.token_digest(token) if token else None
    from app.db.models import Session as SessionRow

    rows = db.scalars(
        select(SessionRow)
        .where(SessionRow.user_id == user.id, SessionRow.revoked_at.is_(None))
        .order_by(SessionRow.last_seen_at.desc())
    ).all()
    return [
        SessionItem(
            id=row.id,
            created_at=row.created_at,
            last_seen_at=row.last_seen_at,
            expires_at=row.expires_at,
            user_agent=row.user_agent,
            current=row.token_hash == this_hash,
        )
        for row in rows
    ]


@router.post("/password", status_code=204)
def change_password(
    payload: PasswordChangeRequest,
    request: Request,
    response: Response,
    db: DbSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Response:
    """Change your own password. Requires the current one.

    Requiring the old password is what stops a borrowed unlocked laptop from
    becoming a permanent takeover, and it is why this cannot be done from the
    Editors tab even by an administrator.
    """
    if not passwords.verify_password(user.password_hash, payload.current_password):
        logger.warning("Password change refused for user %s: current password wrong.", user.id)
        raise HTTPException(status_code=403, detail="Your current password is not right.")

    try:
        passwords.check_strength(payload.new_password, email=user.email)
    except passwords.WeakPassword as weak:
        raise HTTPException(status_code=422, detail=str(weak)) from weak

    user.password_hash = passwords.hash_password(payload.new_password)
    from datetime import UTC, datetime

    user.password_updated_at = datetime.now(UTC)

    # Every other session is now suspect: if the old password was known to
    # somebody, so were the sessions it opened. This one is kept so changing a
    # password does not sign you out of the tab you changed it in.
    current = sessions.active_session(db, request.cookies.get(sessions.SESSION_COOKIE) or "")
    revoked = sessions.revoke_all_for_user(db, user, except_id=current.id if current else None)
    add_audit_log(db, user, "auth.changed_password", "user", user.id, {"sessions_ended": revoked})
    db.commit()
    return Response(status_code=204)
