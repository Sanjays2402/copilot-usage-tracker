"""Tests for user pseudonymization."""

import re

from copilot_usage_tracker.privacy import pseudonym, pseudonym_id


def test_pseudonym_deterministic():
    assert pseudonym("Alice", "salt") == pseudonym("alice", "salt")
    assert pseudonym("alice", "salt") == pseudonym(" alice ", "salt")


def test_pseudonym_salt_sensitive():
    assert pseudonym("alice", "salt1") != pseudonym("alice", "salt2")


def test_pseudonym_format():
    assert re.fullmatch(r"user_[0-9a-f]{12}", pseudonym("alice", "salt"))


def test_pseudonym_differs_per_user():
    assert pseudonym("alice", "salt") != pseudonym("bob", "salt")


def test_pseudonym_id_stable_and_bounded():
    a = pseudonym_id(12345, "salt")
    assert a == pseudonym_id(12345, "salt")
    assert 0 <= a < 2**31
    assert pseudonym_id(12345, "salt") != pseudonym_id(99999, "salt")
