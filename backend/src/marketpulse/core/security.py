"""Password hashing with Argon2id (blueprint 15.1).

Argon2id is the modern adaptive memory-hard scheme recommended for password
storage. We use ``argon2-cffi`` directly rather than passlib (which is effectively
unmaintained as of 2026) and pin conservative production-safe parameters. The
library performs verification with constant-time comparison, so callers must not
add their own early-exit comparisons on the plaintext.

Phase 1 uses this only to seed the ``users`` table honestly and to prove the
password-hash column works end to end. Phase 2 wires it into the real auth flow.
The functions live in ``core`` (not in a model or SQLAlchemy event) so hashing
never happens implicitly and can never be triggered by an accidental load.
"""

from __future__ import annotations

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError

# OWASP-recommended Argon2id minimums (2026): time cost 3, 64 MiB memory, 2 lanes.
# The argon2-cffi defaults are already safe; we pin them so a library bump cannot
# silently weaken production hashes. Raising these later invalidates nothing:
# verify() reads the parameters encoded in each hash.
_hasher = PasswordHasher(time_cost=3, memory_cost=65536, parallelism=2)


def hash_password(plaintext: str) -> str:
    """Return an Argon2id hash string for a plaintext password.

    Raises ValueError on an empty password: an empty password is a caller bug,
    not a hashable input.
    """
    if not plaintext:
        raise ValueError("password must not be empty")
    return _hasher.hash(plaintext)


def verify_password(hashed: str, plaintext: str) -> bool:
    """True only if ``plaintext`` matches the Argon2id ``hashed`` string.

    Never raises on a wrong password or a malformed hash: callers must branch on
    the boolean, never on an exception type, so an attacker cannot distinguish
    'no such user' from 'wrong password' from 'corrupt hash' via error behaviour.
    """
    try:
        return _hasher.verify(hashed, plaintext)
    except VerificationError:
        # VerifyMismatchError is a subclass of VerificationError, so a wrong
        # password is covered here. Never raise on a wrong or malformed hash.
        return False
    except InvalidHashError:
        return False


def needs_rehash(hashed: str) -> bool:
    """True if ``hashed`` was produced with weaker parameters than the current hasher.

    Phase 2's login flow calls this on every successful verify and transparently
    re-hashes; included now so the contract is stable.
    """
    return _hasher.check_needs_rehash(hashed)
