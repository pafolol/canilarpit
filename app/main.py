from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from app.api.router import api_router
from app.api.routes.health import router as health_router
from app.core.config import settings
from app.core.rate_limit import limiter

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
app.include_router(health_router)
app.include_router(api_router, prefix=settings.api_v1_prefix)


@app.get("/", include_in_schema=False)
def root() -> dict[str, str]:
    return {"name": settings.app_name, "docs": "/docs"}
