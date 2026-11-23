"""Unit tests for Argon2id password hashing (blueprint 15.1)."""

from __future__ import annotations

import pytest

from marketpulse.core.security import hash_password, needs_rehash, verify_password


def test_hash_and_verify_roundtrip() -> None:
    hashed = hash_password("correct horse battery staple")
    assert hashed.startswith("$argon2id$")
    assert verify_password(hashed, "correct horse battery staple") is True


def test_wrong_password_does_not_verify() -> None:
    hashed = hash_password("the-real-secret")
    assert verify_password(hashed, "the-wrong-secret") is False


def test_malformed_hash_returns_false_not_raises() -> None:
    # A caller must branch on the boolean, never on an exception type.
    assert verify_password("not-a-real-hash", "anything") is False


def test_empty_password_is_rejected_at_hash_time() -> None:
    with pytest.raises(ValueError):
        hash_password("")


def test_two_hashes_of_the_same_password_differ() -> None:
    assert hash_password("same-password") != hash_password("same-password")


def test_needs_rehash_is_false_for_a_fresh_hash() -> None:
    assert needs_rehash(hash_password("x")) is False
