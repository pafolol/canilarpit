"""Turning a password into something a stolen database does not give away.

Argon2id, with argon2-cffi's defaults, which track the OWASP guidance and are
chosen to be slow on a GPU rather than merely slow. The hash string carries its
own salt and parameters, so a row is self-describing and the cost can be raised
later without a migration: `verify` reports when a hash was made under weaker
settings and the caller rewrites it on the next successful sign-in.

Two things here are about the attacker rather than the user:

  - `verify_dummy` burns the same work as a real check when no account matched,
    so the time a login takes does not answer "does this address have an
    account here?"
  - Nothing in this module logs, formats or returns the password, including on
    the error paths.
"""

import hmac
import unicodedata

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

# Long enough that a person cannot be locked out by a sensible passphrase, short
# enough that nobody hands the hasher a megabyte to chew on.
MIN_PASSWORD_LENGTH = 12
MAX_PASSWORD_LENGTH = 1024

hasher = PasswordHasher()

# A real Argon2id hash of a value nobody knows, used to spend the same time on a
# missing account as on a present one. Generated once at import.
DUMMY_HASH = hasher.hash("no-account-with-this-address")


def normalize(password: str) -> str:
    """NFKC, so a passphrase typed on another keyboard still matches.

    Composed and decomposed forms of the same accented character are different
    byte strings and would otherwise hash differently.
    """
    return unicodedata.normalize("NFKC", password)


class WeakPassword(ValueError):
    """Raised with a message meant to be shown to the person choosing one."""


def check_strength(password: str, *, email: str | None = None) -> None:
    """The floor, not a policy of arbitrary characters.

    Length is what actually resists guessing; composition rules mostly produce
    `Password1!`. The one content rule is that the password may not be the
    address it signs in with, because that is the first thing anybody tries.
    """
    if len(password) < MIN_PASSWORD_LENGTH:
        raise WeakPassword(
            f"Use at least {MIN_PASSWORD_LENGTH} characters. A short phrase you can "
            "remember beats a short word with symbols in it."
        )
    if len(password) > MAX_PASSWORD_LENGTH:
        raise WeakPassword(f"That is over {MAX_PASSWORD_LENGTH} characters.")
    if not password.strip():
        raise WeakPassword("That is only whitespace.")
    if email and password.strip().lower() == email.strip().lower():
        raise WeakPassword("That is your email address. Choose something else.")


def hash_password(password: str) -> str:
    return hasher.hash(normalize(password))


def verify_password(password_hash: str | None, password: str) -> bool:
    """True when the password matches. Constant work either way.

    A user row with no password - the seeder, a development identity - cannot be
    signed in to with one, and still costs a full verify so that its existence
    is not detectable by how fast it is refused.
    """
    if not password_hash:
        verify_dummy()
        return False
    try:
        return hasher.verify(password_hash, normalize(password))
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


def verify_dummy() -> None:
    """Spend a verification's worth of time on nothing."""
    try:
        hasher.verify(DUMMY_HASH, "wrong")
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        pass


def needs_rehash(password_hash: str) -> bool:
    """Whether this hash predates the current cost settings."""
    try:
        return hasher.check_needs_rehash(password_hash)
    except InvalidHashError:
        return True


def constant_time_equals(left: str, right: str) -> bool:
    """For comparing tokens we hold both sides of, such as the CSRF pair."""
    return hmac.compare_digest(left.encode("utf-8"), right.encode("utf-8"))
