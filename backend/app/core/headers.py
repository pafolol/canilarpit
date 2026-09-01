"""Response headers, and the content policy every page ships with.

A browser only enforces what it is told to enforce. Every response leaves with
the same baseline — no sniffing, no framing, no referrer leakage, no ambient
device permissions — and, in production, HSTS.

The content policy is the same everywhere, and it is the narrow one:
`script-src 'self'`, no eval, no third-party origin. That is possible because
sign-in is a form this application serves. Nothing is loaded from anywhere
else, by the panel or by the reading interface, so neither has to be widened
for the other - and a deployment that does need an extra origin adds it
explicitly through CSP_EXTRA_ORIGINS rather than by loosening the default.

Admin JSON also leaves with `Cache-Control: no-store`, so a draft that has not
been published cannot come to rest in a proxy on the way back.
"""

from collections.abc import Awaitable, Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.core.config import settings

# Paths whose responses must not be stored anywhere: unpublished drafts, the
# editorial queue, reader submissions, and the signed-in account itself.
PRIVATE_PREFIXES = (
    f"{settings.api_v1_prefix}/admin",
    f"{settings.api_v1_prefix}/me",
)

PERMISSIONS_POLICY = ", ".join(
    f"{feature}=()"
    for feature in (
        "accelerometer",
        "autoplay",
        "camera",
        "display-capture",
        "encrypted-media",
        "geolocation",
        "gyroscope",
        "magnetometer",
        "microphone",
        "midi",
        "payment",
        "usb",
    )
)


def is_admin_path(path: str) -> bool:
    """The panel itself, and the API it talks to."""
    return path == "/admin" or path.startswith(("/admin/", f"{settings.api_v1_prefix}/admin"))


def content_security_policy(path: str) -> str:
    """One policy, and it is the tight one.

    `path` is still taken so a deployment that has to widen the panel can do it
    here without the reading interface inheriting the change.
    """
    extra = settings.admin_script_origins if is_admin_path(path) else []
    script = ["'self'", *extra]
    connect = ["'self'", *extra]
    frame = ["'self'", *extra] if extra else ["'none'"]

    directives: dict[str, list[str]] = {
        "default-src": ["'none'"],
        "base-uri": ["'self'"],
        "form-action": ["'self'"],
        "frame-ancestors": ["'none'"],
        "object-src": ["'none'"],
        "script-src": script,
        # The app sets inline styles, and the shell pulls IBM Plex from Google.
        "style-src": ["'self'", "'unsafe-inline'", "https://fonts.googleapis.com"],
        "font-src": ["'self'", "https://fonts.gstatic.com", "data:"],
        # Pictures come from six image providers and object storage, so the
        # host cannot be enumerated here. The scheme still can be.
        "img-src": ["'self'", "data:", "blob:", "https:"],
        "connect-src": connect,
        "worker-src": ["'self'", "blob:"],
        "manifest-src": ["'self'"],
        "frame-src": frame,
    }

    policy = "; ".join(f"{name} {' '.join(values)}" for name, values in directives.items())
    if settings.is_production:
        policy += "; upgrade-insecure-requests"
    return policy


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        response = await call_next(request)
        headers = response.headers

        headers.setdefault("X-Content-Type-Options", "nosniff")
        headers.setdefault("X-Frame-Options", "DENY")
        headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        headers.setdefault("Permissions-Policy", PERMISSIONS_POLICY)
        # Nothing signs in through a popup any more, so this stays strict
        # everywhere: a window this page opens cannot reach back into it.
        headers.setdefault("Cross-Origin-Opener-Policy", "same-origin")
        headers.setdefault("Cross-Origin-Resource-Policy", "same-origin")
        headers.setdefault("X-Permitted-Cross-Domain-Policies", "none")

        policy_header = (
            "Content-Security-Policy-Report-Only"
            if settings.csp_report_only
            else "Content-Security-Policy"
        )
        headers.setdefault(policy_header, content_security_policy(request.url.path))

        if settings.is_production:
            headers.setdefault(
                "Strict-Transport-Security",
                f"max-age={settings.hsts_max_age_seconds}; includeSubDomains",
            )

        if request.url.path.startswith(PRIVATE_PREFIXES):
            headers["Cache-Control"] = "no-store, no-cache, must-revalidate, private"
            headers["Pragma"] = "no-cache"

        return response
