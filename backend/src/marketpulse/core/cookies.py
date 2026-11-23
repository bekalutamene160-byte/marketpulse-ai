"""Cookie and CSRF constants shared by the API layer and the session resolver.

Pure constants and helpers with no framework imports, so both ``infrastructure``
(the resolver that READS the cookie) and ``api`` (the routers that SET and CLEAR it)
can depend on them without importing each other (blueprint 5.4 dependency direction).

The session cookie value is an opaque random token; only its SHA-256 hex digest is
stored in ``auth_sessions`` (migration 0002). The CSRF token uses the same shape and
is bound to the session row via ``csrf_token_hash``; the browser holds it in a
readable cookie so the single-page app can echo it back in the ``X-CSRF-Token``
header on every authenticated state change (blueprint 15.1).
"""

from __future__ import annotations

import hashlib
import hmac

SESSION_COOKIE = "mp_session"
CSRF_COOKIE = "mp_csrf"
CSRF_HEADER = "X-CSRF-Token"

#: SHA-256 produces 64 hex characters; the column is VARCHAR(64) to match exactly.
TOKEN_HASH_LENGTH = 64


def hash_token(token: str) -> str:
    """SHA-256 hex digest of a token. Deterministic so lookups can use the hash."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def token_hashes_match(presented_token: str, stored_hash: str) -> bool:
    """Constant-time comparison of sha256(presented) against the stored digest.

    A plain ``==`` on digests would leak timing information about the stored value;
    ``hmac.compare_digest`` is the standard constant-time string comparison.
    """
    return hmac.compare_digest(hash_token(presented_token), stored_hash)


def parse_cookie_header(cookie_header: str) -> dict[str, str]:
    """Parse a raw ``Cookie: a=b; c=d`` header into a plain dict.

    Uses only the stdlib so the resolver stays framework-free. Malformed pairs are
    skipped rather than raising: a broken cookie must resolve to "no session", not
    to a 500.
    """
    from http.cookies import SimpleCookie

    cookie = SimpleCookie()
    try:
        cookie.load(cookie_header)
    except Exception:  # noqa: BLE001 - any parse failure means "no usable cookies"
        return {}
    return {morsel.key: morsel.value for morsel in cookie.values()}


__all__ = [
    "CSRF_COOKIE",
    "CSRF_HEADER",
    "SESSION_COOKIE",
    "TOKEN_HASH_LENGTH",
    "hash_token",
    "parse_cookie_header",
    "token_hashes_match",
]
