import logging

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import JSONResponse
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from sqlalchemy.exc import OperationalError

from app.api.router import api_router
from app.api.routes.health import router as health_router
from app.api.routes.site import mount_frontend
from app.core.config import settings
from app.core.headers import SecurityHeadersMiddleware
from app.core.rate_limit import limiter
from app.services import sessions

logger = logging.getLogger(__name__)

# The identity headers the local sign-in uses. They are only ever advertised to
# a browser when the bypass that reads them is actually on, so a production
# deployment does not tell anybody the mechanism exists.
DEV_IDENTITY_HEADERS = ["X-Dev-User", "X-Dev-Email", "X-Dev-Display-Name"]


def cors_headers() -> list[str]:
    # The session travels in a cookie the browser attaches itself, so no
    # Authorization header is needed. X-CSRF-Token is: the panel echoes the
    # readable half of the cookie pair back, which is what a cross-site form
    # cannot do.
    headers = ["Content-Type", sessions.CSRF_HEADER]
    if settings.dev_auth_bypass and not settings.is_production:
        headers += DEV_IDENTITY_HEADERS
    return headers


def create_app() -> FastAPI:
    """Build the application for whatever environment it finds itself in.

    A factory rather than a module-level literal because two of the decisions
    here — whether Swagger exists, whether the identity headers are advertised —
    are made once at import and cannot be changed afterwards. A test that wants
    to know how the production app behaves has to be able to build one.
    """
    # Nothing else configures logging, so every logger.warning in the app has
    # been going to Python's last-resort handler or nowhere at all. The auth
    # path in particular explains itself only through these.
    logging.basicConfig(
        level=logging.DEBUG if settings.debug else logging.INFO,
        format="%(levelname)-8s %(name)s: %(message)s",
    )

    docs = settings.api_docs_enabled
    if not docs:
        # Swagger and the schema are a route-by-route map of the admin surface,
        # including which role each one wants. Authentication does not stop
        # somebody reading it, so in production it is simply not served.
        logger.info("API documentation is disabled (APP_ENV=%s).", settings.app_env)

    app = FastAPI(
        title=settings.app_name,
        version="0.1.0",
        debug=settings.debug and not settings.is_production,
        description="Catalog and editorial API for pre-generated Can I LARP It guides.",
        docs_url="/docs" if docs else None,
        redoc_url="/redoc" if docs else None,
        openapi_url="/openapi.json" if docs else None,
    )
    app.state.limiter = limiter
    app.add_exception_handler(
        RateLimitExceeded,
        _rate_limit_exceeded_handler,  # type: ignore[arg-type]
    )

    # Outermost, so a response that leaves down any path — a handled error, a
    # static asset, the single-page app — still leaves with the headers on it.
    app.add_middleware(SecurityHeadersMiddleware)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.frontend_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=cors_headers(),
        max_age=600,
    )

    # Opt-in: an incomplete list here answers 400 to everything, health checks
    # included, so it is installed only when a deployment has actually said
    # which hosts it answers to.
    if settings.trusted_hosts:
        app.add_middleware(TrustedHostMiddleware, allowed_hosts=settings.trusted_hosts)

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
    return app


app = create_app()

# Last, and on purpose: the frontend's catch-all would otherwise swallow
# /api/v1/*, /health, /docs and /openapi.json. With no build on disk nothing is
# mounted at all, and the API answers at the root as it always did.
frontend_mounted = mount_frontend(app)

if not frontend_mounted:

    @app.get("/", include_in_schema=False)
    def root() -> dict[str, str]:
        body = {"name": settings.app_name}
        if settings.api_docs_enabled:
            body["docs"] = "/docs"
        return body
