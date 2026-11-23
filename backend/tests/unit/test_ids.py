"""Unit tests for identity helpers (core/ids.py)."""

from __future__ import annotations

import uuid

from marketpulse.core.ids import is_valid_uuid_str, new_id


def test_new_id_is_a_uuid4() -> None:
    i = new_id()
    assert isinstance(i, uuid.UUID)
    assert i.version == 4


def test_is_valid_uuid_str_accepts_canonical_form() -> None:
    assert is_valid_uuid_str(str(uuid.uuid4())) is True


def test_is_valid_uuid_str_rejects_garbage() -> None:
    assert is_valid_uuid_str("nope") is False
    assert is_valid_uuid_str("") is False
    assert is_valid_uuid_str("550e8400-e29b-41d4-a716-446655440000-trailing") is False
