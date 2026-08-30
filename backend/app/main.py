import logging

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from sqlalchemy.exc import OperationalError

from app.api.router import api_router
from app.api.routes.health import router as health_router
from app.core.config import settings
from app.core.rate_limit import limiter

logger = logging.getLogger(__name__)

app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    debug=settings.debug,
    description="Catalog and editorial API for pre-generated Can I LARP It guides.",
)
app.state.limiter = limiter
app.add_exception_handler(
    RateLimitExceeded,
    _rate_limit_exceeded_handler,  # type: ignore[arg-type]
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.frontend_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=[
        "Authorization",
        "Content-Type",
        "X-Dev-Clerk-User-Id",
        "X-Dev-Email",
        "X-Dev-Display-Name",
    ],
)


@app.exception_handler(OperationalError)
def handle_database_unavailable(request: Request, exc: OperationalError) -> JSONResponse:
    """An unreachable database is a 503, not a 500.

    It is the single most common failure in a fresh checkout, and the frontend
    shows this message verbatim, so it has to say what to do about it.
    """
    logger.warning("Database unavailable for %s %s: %s", request.method, request.url.path, exc)
    return JSONResponse(
        status_code=503,
        content={
            "detail": (
                "The database is unavailable. Check DATABASE_URL, then run "
                "`alembic upgrade head` and `canilarpit seed`."
            )
        },
    )


app.include_router(health_router)
app.include_router(api_router, prefix=settings.api_v1_prefix)


@app.get("/", include_in_schema=False)
def root() -> dict[str, str]:
    return {"name": settings.app_name, "docs": "/docs"}
