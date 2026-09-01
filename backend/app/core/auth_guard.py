"""Throttles for the authenticated surface.

The submission form has its own five obstacles because a stranger can reach it.
The admin surface is the opposite problem: everything behind it is already
signed in, so the thing worth bounding is not volume but *probing* — somebody
walking the route table with a stolen or guessed credential, or a compromised
editor session being drained at machine speed.

Two counters, both keyed on the anonymous client hash the submission form
already derives, so no raw address is stored here either:

  - failed authentications, which is the signal that somebody is trying
    credentials rather than using one;
  - admin requests overall, which bounds what a live session can do per minute.

Both are per-process and in memory. That is deliberate: this is a speed bump in
front of an endpoint that is *already* authenticated, not the authentication
itself, and a counter that needs a round trip to Postgres to decide whether to
answer is a denial-of-service vector of its own. Behind two workers the real
limit is twice the configured one; that is a factor of two, not a hole.
"""

import time
from collections import OrderedDict, deque

from fastapi import Depends, HTTPException, Request, status

from app.core.antiabuse import client_hash
from app.core.config import settings

# Bounded so a flood of distinct clients cannot grow this without limit. The
# oldest key is evicted, which at worst forgives somebody who stopped anyway.
MAX_TRACKED_CLIENTS = 8192


class SlidingWindow:
    """Counts hits per key over a moving window, forgetting as it goes."""

    def __init__(self, max_keys: int = MAX_TRACKED_CLIENTS) -> None:
        self._hits: OrderedDict[str, deque[float]] = OrderedDict()
        self._max_keys = max_keys

    def hit(self, key: str, limit: int, window_seconds: float) -> bool:
        """Record an attempt. False once the key is over its limit."""
        if limit <= 0:
            return True
        now = time.monotonic()
        timestamps = self._hits.get(key)
        if timestamps is None:
            timestamps = deque()
            self._hits[key] = timestamps
        self._hits.move_to_end(key)

        cutoff = now - window_seconds
        while timestamps and timestamps[0] < cutoff:
            timestamps.popleft()

        while len(self._hits) > self._max_keys:
            self._hits.popitem(last=False)

        if len(timestamps) >= limit:
            return False
        timestamps.append(now)
        return True

    def forget(self, key: str) -> None:
        """Drop a key's history. Called when an attempt finally succeeds."""
        self._hits.pop(key, None)

    def clear(self) -> None:
        self._hits.clear()


auth_failures = SlidingWindow()
account_failures = SlidingWindow()
admin_requests = SlidingWindow()


def retry_after(seconds: int) -> dict[str, str]:
    return {"Retry-After": str(seconds)}


def guard_auth_attempts(request: Request) -> str:
    """Refuse a client that has been failing authentication, before verifying.

    Checked *before* the signature is, so a client that is grinding tokens stops
    paying for JWKS work and stops getting an oracle out of the difference
    between "expired" and "wrong issuer".
    """
    client = client_hash(request)
    if not auth_failures.hit(client, settings.auth_failures_per_minute, 60.0):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many failed sign-in attempts. Wait a minute and try again.",
            headers=retry_after(60),
        )
    return client


def record_auth_success(client: str) -> None:
    """A real credential clears the client's failure history."""
    auth_failures.forget(client)


def guard_account(email: str) -> None:
    """A second counter, on the account rather than the caller.

    The per-client limit is beaten by moving address; the per-account limit is
    not, because the account being attacked stays the same wherever the guesses
    come from. Keyed on the address as typed-and-lowered, so it applies before
    we know whether the account exists - otherwise the difference between being
    throttled and not would answer that question by itself.
    """
    if not account_failures.hit(email.lower(), settings.account_failures_per_minute, 60.0):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many sign-in attempts for this account. Wait a minute and try again.",
            headers=retry_after(60),
        )


def record_account_success(email: str) -> None:
    account_failures.forget(email.lower())


def admin_throttle(request: Request) -> None:
    """A ceiling on the admin surface as a whole, applied by the router.

    Sits on the router rather than on each route so a new endpoint is covered
    the day it is written rather than the day somebody remembers.
    """
    if not admin_requests.hit(
        client_hash(request), settings.admin_requests_per_minute, 60.0
    ):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many admin requests. Slow down and retry shortly.",
            headers=retry_after(30),
        )


AdminThrottle = Depends(admin_throttle)
