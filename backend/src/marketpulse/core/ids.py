"""Identity helpers (blueprint 5.4: core/ids.py).

UUIDs are the public identifier shape for every tenant-scoped entity. They are
non-enumerable (an attacker cannot walk IDs to probe a neighbor tenant) and
independent of insertion order. Time-ordered UUIDs would improve index locality,
but ``uuid7`` is not in the Python 3.12 stdlib; ``created_at`` columns carry the
ordering responsibility instead, and a partial index on time covers history scans.
"""

from __future__ import annotations

import re
import uuid

# A canonical UUID string is the only shape accepted from clients when a resource
# ID is echoed back. Keeping it strict prevents IDOR-style probing with malformed
# values and makes every log line greppable. Case-insensitive on purpose: Postgres
# lowercases UUID text on output, but humans paste uppercase.
_UUID_STR = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.IGNORECASE
)


def new_id() -> uuid.UUID:
    """Generate a fresh random UUID (uuid4)."""
    return uuid.uuid4()


def is_valid_uuid_str(value: str) -> bool:
    """True only for a canonical UUID string. Used to validate client-supplied IDs."""
    return bool(_UUID_STR.match(value))
