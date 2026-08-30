from functools import lru_cache

import jwt
from fastapi import Depends, Header, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt import PyJWKClient
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.models import User, UserRole
from app.db.session import get_db

bearer_scheme = HTTPBearer(auto_error=False)


@lru_cache
def get_jwk_client() -> PyJWKClient:
    if not settings.clerk_jwks_url:
        raise RuntimeError("CLERK_JWKS_URL is not configured")
    return PyJWKClient(settings.clerk_jwks_url, cache_keys=True)


def decode_clerk_token(token: str) -> dict:
    if not settings.clerk_issuer or not settings.clerk_jwks_url:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Clerk authentication is not configured",
        )
    try:
        signing_key = get_jwk_client().get_signing_key_from_jwt(token)
        claims = jwt.decode(
            token,
            signing_key.key,
            algorithms=["RS256"],
            issuer=settings.clerk_issuer,
            audience=settings.clerk_audience,
            options={"verify_aud": settings.clerk_audience is not None},
            leeway=10,
        )
        validate_authorized_party(claims)
        return claims
    except jwt.PyJWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired authentication token",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc


def validate_authorized_party(claims: dict) -> None:
    if not settings.clerk_authorized_parties:
        return
    authorized_party = claims.get("azp")
    if authorized_party not in settings.clerk_authorized_parties:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication token has an unauthorized party",
            headers={"WWW-Authenticate": "Bearer"},
        )


def sync_user_from_claims(db: Session, claims: dict) -> User:
    clerk_user_id = claims.get("sub")
    if not clerk_user_id:
        raise HTTPException(status_code=401, detail="Authentication token has no subject")

    display_name = claims.get("name") or claims.get("username")
    inserted_id = db.execute(
        pg_insert(User)
        .values(
            clerk_user_id=clerk_user_id,
            email=claims.get("email"),
            display_name=display_name,
            avatar_url=claims.get("picture") or claims.get("image_url"),
        )
        .on_conflict_do_nothing(index_elements=[User.clerk_user_id])
        .returning(User.id)
    ).scalar_one_or_none()
    user = (
        db.get(User, inserted_id)
        if inserted_id
        else db.scalar(select(User).where(User.clerk_user_id == clerk_user_id))
    )
    if user is None:
        db.rollback()
        raise HTTPException(status_code=500, detail="Unable to synchronize authenticated user")
    db.commit()
    return user


def get_optional_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: Session = Depends(get_db),
    x_dev_clerk_user_id: str | None = Header(default=None),
    x_dev_email: str | None = Header(default=None),
) -> User | None:
    if credentials:
        return sync_user_from_claims(db, decode_clerk_token(credentials.credentials))

    if settings.dev_auth_bypass and x_dev_clerk_user_id:
        return sync_user_from_claims(
            db,
            {
                "sub": x_dev_clerk_user_id,
                "email": x_dev_email,
                "name": request.headers.get("X-Dev-Display-Name"),
            },
        )
    return None


def get_current_user(user: User | None = Depends(get_optional_user)) -> User:
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
            headers={"WWW-Authenticate": "Bearer"},
        )
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
