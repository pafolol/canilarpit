"""What the admin surface refuses, and what it refuses to start without.

Every test here is a door somebody could otherwise walk through: a password
guessed from a thousand addresses, a sign-in form that says which half was
wrong, a form on another site posting with your cookie attached, a wildcard
CORS origin handing an authenticated session to any site that asks.
"""

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from starlette.requests import Request
from starlette.responses import Response

from app.core import auth_guard
from app.core.config import Settings, settings
from app.core.headers import content_security_policy
from app.core.security import dev_identity_allowed
from app.main import app, create_app
from app.services import passwords, sessions


def production_settings(**overrides) -> Settings:
    """A settings object built as a deployment would build it."""
    base = {
        "app_env": "production",
        "dev_auth_bypass": False,
        "submission_secret": "a-real-secret",
        "frontend_origins": ["https://canilarpit.com"],
        "site_base_url": "https://canilarpit.com",
    }
    return Settings(_env_file=None, **{**base, **overrides})


def fake_request(method: str = "POST", cookies: dict | None = None, headers: dict | None = None):
    raw = [
        (key.lower().encode(), value.encode()) for key, value in (headers or {}).items()
    ]
    if cookies:
        jar = "; ".join(f"{k}={v}" for k, v in cookies.items())
        raw.append((b"cookie", jar.encode()))
    return Request({"type": "http", "method": method, "path": "/", "headers": raw})


# ------------------------------------------------------------- the password


def test_a_password_is_never_stored_and_never_recoverable() -> None:
    hashed = passwords.hash_password("a decent passphrase here")
    assert "a decent passphrase here" not in hashed
    assert hashed.startswith("$argon2id$")
    assert passwords.verify_password(hashed, "a decent passphrase here")
    assert not passwords.verify_password(hashed, "a decent passphrase HERE")


def test_the_same_password_hashes_differently_every_time() -> None:
    """A per-row salt, so one cracked hash is one account and not the table."""
    first = passwords.hash_password("a decent passphrase here")
    second = passwords.hash_password("a decent passphrase here")
    assert first != second


def test_an_account_with_no_password_cannot_be_signed_in_to() -> None:
    """The seeder and the development identities have no password by design."""
    assert passwords.verify_password(None, "") is False
    assert passwords.verify_password(None, "anything at all") is False


def test_the_password_floor_is_length_rather_than_punctuation() -> None:
    with pytest.raises(passwords.WeakPassword, match="at least"):
        passwords.check_strength("short")
    with pytest.raises(passwords.WeakPassword, match="email address"):
        passwords.check_strength("editor@example.com", email="Editor@Example.com")
    passwords.check_strength("a long enough passphrase")


def test_unicode_forms_of_one_passphrase_still_match() -> None:
    """Composed and decomposed accents are different bytes and one password."""
    composed = "café pass phrase"
    decomposed = "café pass phrase"
    assert passwords.verify_password(passwords.hash_password(composed), decomposed)


# -------------------------------------------------------------- the session


def test_the_session_cookie_is_never_stored_in_the_clear() -> None:
    """A copy of the table is not a set of working sessions."""
    digest = sessions.token_digest("a-token")
    assert digest != "a-token"
    assert len(digest) == 64
    assert sessions.token_digest("a-token") == digest


def test_the_session_cookie_cannot_be_read_by_javascript() -> None:
    response = Response()
    sessions.attach(response, "session-token", "csrf-token")
    cookies = response.headers.getlist("set-cookie")
    session_cookie = next(c for c in cookies if c.startswith(sessions.SESSION_COOKIE))
    csrf_cookie = next(c for c in cookies if c.startswith(sessions.CSRF_COOKIE))

    assert "httponly" in session_cookie.lower()
    assert "samesite=lax" in session_cookie.lower()
    # The CSRF half is readable on purpose: the panel has to echo it back.
    assert "httponly" not in csrf_cookie.lower()


def test_a_write_needs_both_halves_of_the_csrf_pair() -> None:
    """Another origin can send our cookie. It cannot read it, so it cannot
    produce the header, and both have to agree."""
    assert sessions.csrf_ok(fake_request("GET")) is True

    assert sessions.csrf_ok(fake_request("POST")) is False
    assert sessions.csrf_ok(fake_request("POST", cookies={sessions.CSRF_COOKIE: "abc"})) is False
    assert (
        sessions.csrf_ok(fake_request("POST", headers={sessions.CSRF_HEADER: "abc"})) is False
    )
    assert (
        sessions.csrf_ok(
            fake_request(
                "POST",
                cookies={sessions.CSRF_COOKIE: "abc"},
                headers={sessions.CSRF_HEADER: "different"},
            )
        )
        is False
    )
    assert (
        sessions.csrf_ok(
            fake_request(
                "POST",
                cookies={sessions.CSRF_COOKIE: "abc"},
                headers={sessions.CSRF_HEADER: "abc"},
            )
        )
        is True
    )


# ------------------------------------------------------------ the throttles


def test_an_account_is_throttled_however_many_addresses_try_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Moving address beats the per-client limit. It does not beat this one."""
    auth_guard.account_failures.clear()
    monkeypatch.setattr(settings, "account_failures_per_minute", 3)

    for _ in range(3):
        auth_guard.guard_account("victim@example.com")
    with pytest.raises(HTTPException) as error:
        auth_guard.guard_account("victim@example.com")
    assert error.value.status_code == 429

    # Case is not a way around it.
    with pytest.raises(HTTPException):
        auth_guard.guard_account("VICTIM@EXAMPLE.COM")

    auth_guard.record_account_success("victim@example.com")
    auth_guard.guard_account("victim@example.com")
    auth_guard.account_failures.clear()


def test_the_admin_surface_has_a_ceiling(monkeypatch: pytest.MonkeyPatch) -> None:
    auth_guard.admin_requests.clear()
    monkeypatch.setattr(settings, "admin_requests_per_minute", 3)
    client = TestClient(app)

    for _ in range(3):
        assert client.get("/api/v1/admin/guides").status_code in {401, 403}

    refused = client.get("/api/v1/admin/guides")
    assert refused.status_code == 429
    assert refused.headers["Retry-After"]
    auth_guard.admin_requests.clear()


def test_failed_sign_ins_are_counted_and_then_forgiven() -> None:
    window = auth_guard.SlidingWindow()
    assert all(window.hit("client", 3, 60.0) for _ in range(3))
    assert window.hit("client", 3, 60.0) is False
    window.forget("client")
    assert window.hit("client", 3, 60.0) is True


def test_the_window_forgets_the_oldest_client_rather_than_growing() -> None:
    window = auth_guard.SlidingWindow(max_keys=4)
    for index in range(50):
        window.hit(f"client-{index}", 10, 60.0)
    assert len(window._hits) <= 4


# ------------------------------------------------------------- the settings


def test_the_development_bypass_cannot_be_on_in_production(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The settings validator refuses to build it; this refuses to use it."""
    monkeypatch.setattr(settings, "dev_auth_bypass", True)
    monkeypatch.setattr(settings, "app_env", "development")
    assert dev_identity_allowed() is True

    monkeypatch.setattr(settings, "app_env", "production")
    assert dev_identity_allowed() is False

    with pytest.raises(ValueError, match="DEV_AUTH_BYPASS"):
        production_settings(dev_auth_bypass=True)


def test_production_refuses_a_wildcard_or_cleartext_origin() -> None:
    """`allow_credentials` plus `*` is how an admin session reaches everybody."""
    with pytest.raises(ValueError, match="cannot contain"):
        production_settings(frontend_origins=["*"])
    with pytest.raises(ValueError, match="must be https"):
        production_settings(frontend_origins=["http://canilarpit.com"])
    with pytest.raises(ValueError, match="SITE_BASE_URL must be https"):
        production_settings(site_base_url="http://canilarpit.com")


def test_production_needs_a_real_submission_secret() -> None:
    with pytest.raises(ValueError, match="SUBMISSION_SECRET"):
        production_settings(submission_secret="dev-only-change-me")


def test_a_valid_production_configuration_builds() -> None:
    built = production_settings()
    assert built.is_production
    assert built.api_docs_enabled is False


# ----------------------------------------------------------- what ships out


def test_every_response_carries_the_baseline_headers() -> None:
    response = TestClient(app).get("/health/live")
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["X-Frame-Options"] == "DENY"
    assert response.headers["Referrer-Policy"] == "strict-origin-when-cross-origin"
    assert "camera=()" in response.headers["Permissions-Policy"]
    assert "frame-ancestors 'none'" in response.headers["Content-Security-Policy"]


def test_no_page_needs_third_party_script() -> None:
    """Sign-in is served by this application, so the policy stays narrow.

    Nothing loads code from anywhere else any more, which is why `/admin` gets
    the same `script-src 'self'` as the pages a stranger opens.
    """
    for path in ("/entry/naruto", "/admin", "/api/v1/admin/guides"):
        policy = content_security_policy(path)
        assert "script-src 'self'" in policy
        assert "unsafe-eval" not in policy


def test_admin_responses_are_never_stored() -> None:
    """An unpublished draft coming to rest in a proxy is a leak."""
    response = TestClient(app).get("/api/v1/admin/guides")
    assert response.status_code in {401, 403}
    assert "no-store" in response.headers["Cache-Control"]


def test_production_serves_no_swagger_and_no_schema(monkeypatch: pytest.MonkeyPatch) -> None:
    """Authentication does not stop anybody reading a map of the admin surface."""
    monkeypatch.setattr(settings, "app_env", "production")
    monkeypatch.setattr(settings, "dev_auth_bypass", False)
    client = TestClient(create_app())
    for path in ("/docs", "/redoc", "/openapi.json"):
        assert client.get(path).status_code == 404


def test_production_does_not_advertise_the_identity_headers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.main import cors_headers

    monkeypatch.setattr(settings, "dev_auth_bypass", True)
    monkeypatch.setattr(settings, "app_env", "development")
    assert "X-Dev-User" in cors_headers()

    monkeypatch.setattr(settings, "app_env", "production")
    assert cors_headers() == ["Content-Type", sessions.CSRF_HEADER]


def test_there_is_no_registration_endpoint() -> None:
    """Accounts are made by an administrator. A stranger cannot make one."""
    paths = app.openapi()["paths"]
    assert "/api/v1/auth/login" in paths
    for path in paths:
        assert "register" not in path
        assert "sign-up" not in path
        assert "signup" not in path
