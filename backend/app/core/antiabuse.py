"""Keeping an open, unauthenticated write endpoint usable.

The submission form is the only place a stranger can put text into the editorial
queue, so it gets five independent obstacles rather than one good one. Any single
measure here is beatable by somebody determined; together they make casual abuse
more effort than it is worth, and every one of them fails closed.

  1. A signed form token, so a submission has to have visited the form.
  2. A minimum time between fetching the form and sending it, because scripts
     are fast and people are not.
  3. A honeypot field that a browser never fills and a naive bot always does.
  4. Rate limits per address, and a database quota per client hash which
     survives a restart in a way an in-memory limiter does not.
  5. Content heuristics: length, variety, and how much of it is links.

The client hash is HMAC-SHA256 of address plus user agent under a server secret.
No raw address is stored anywhere. It is enough to count against and to block,
and useless for identifying a person.
"""

import hashlib
import hmac
import re
import time
from dataclasses import dataclass

from fastapi import HTTPException, Request, status

from app.core.config import settings

TOKEN_VERSION = "v1"


def _secret() -> bytes:
    return settings.submission_secret.encode("utf-8")


def client_hash(request: Request) -> str:
    """A stable, anonymous handle for one browser on one connection."""
    address = request.client.host if request.client else "unknown"
    # A proxy header is trusted only when the deployment says it sits behind one,
    # because otherwise anybody can set it and mint a fresh identity per request.
    if settings.trust_forwarded_for:
        forwarded = request.headers.get("x-forwarded-for")
        if forwarded:
            address = forwarded.split(",")[0].strip()

    material = "|".join(
        [
            address,
            request.headers.get("user-agent", ""),
            request.headers.get("accept-language", ""),
        ]
    )
    return hmac.new(_secret(), material.encode("utf-8"), hashlib.sha256).hexdigest()


@dataclass(frozen=True)
class FormToken:
    issued_at: int
    signature: str

    @property
    def value(self) -> str:
        return f"{TOKEN_VERSION}.{self.issued_at}.{self.signature}"


def issue_form_token(client: str) -> FormToken:
    """Bind a token to the client that asked for it, and to the moment it asked."""
    issued_at = int(time.time())
    signature = hmac.new(
        _secret(), f"{TOKEN_VERSION}.{issued_at}.{client}".encode(), hashlib.sha256
    ).hexdigest()
    return FormToken(issued_at=issued_at, signature=signature)


def check_form_token(token: str, client: str) -> None:
    """Reject anything that did not come from this form, from this client, recently."""
    problem = "This form expired. Reload the page and try again."
    parts = token.split(".") if token else []
    if len(parts) != 3 or parts[0] != TOKEN_VERSION:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=problem)

    _, raw_issued, signature = parts
    try:
        issued_at = int(raw_issued)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=problem) from None

    expected = hmac.new(
        _secret(), f"{TOKEN_VERSION}.{issued_at}.{client}".encode(), hashlib.sha256
    ).hexdigest()
    if not hmac.compare_digest(expected, signature):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=problem)

    elapsed = time.time() - issued_at
    if elapsed > settings.submission_token_ttl_seconds:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=problem)
    if elapsed < settings.submission_min_seconds:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="That was faster than anybody reads a form. Take a moment and resend.",
        )


def check_honeypot(value: str | None) -> None:
    """A field the layout hides and a label tells people to leave alone."""
    if value:
        # Say nothing useful: a bot that learns why it failed adapts.
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="This submission was not accepted."
        )


URL_PATTERN = re.compile(r"https?://|www\.", re.IGNORECASE)
REPEAT_PATTERN = re.compile(r"(.)\1{9,}")


def check_notes(notes: str) -> None:
    """Cheap quality gates, run before anything expensive touches the text."""
    cleaned = " ".join(notes.split())
    if len(cleaned) < settings.submission_min_notes:
        raise HTTPException(
            status_code=422,
            detail=(
                f"Tell us a bit more: at least {settings.submission_min_notes} characters "
                "about what somebody would need to know."
            ),
        )

    words = cleaned.split()
    if len(set(word.lower() for word in words)) < min(8, len(words)):
        raise HTTPException(
            status_code=422,
            detail="That reads as repeated text rather than a description.",
        )
    if REPEAT_PATTERN.search(cleaned):
        raise HTTPException(
            status_code=422,
            detail="That reads as repeated text rather than a description.",
        )
    if len(URL_PATTERN.findall(cleaned)) > settings.submission_max_links:
        raise HTTPException(
            status_code=422,
            detail="Too many links. Describe it in your own words instead.",
        )
