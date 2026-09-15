"""Tests for store.user_daily_series — zero-filled per-user daily rows."""

import pytest

from copilot_usage_tracker.store import UsageStore


@pytest.fixture()
def store(tmp_path):
    s = UsageStore(tmp_path / "drill.db")
    s.upsert_user_day(
        "2026-09-01", "acme", 1, user_login="alice", ai_credits_used=100.0, interactions=5
    )
    s.upsert_user_day(
        "2026-09-03", "acme", 1, user_login="alice", ai_credits_used=200.0, interactions=9
    )
    s.upsert_user_day(
        "2026-09-03", "acme", 2, user_login="bob", ai_credits_used=50.0, interactions=2
    )
    return s


def test_fills_missing_days_with_zeros(store):
    rows = store.user_daily_series("alice", "2026-09", "acme")
    assert len(rows) == 30  # every day of September 2026
    assert rows[0] == {"day": "2026-09-01", "credits": 100.0, "interactions": 5}
    assert rows[1] == {"day": "2026-09-02", "credits": 0.0, "interactions": 0}
    assert rows[2] == {"day": "2026-09-03", "credits": 200.0, "interactions": 9}
    assert rows[29]["day"] == "2026-09-30"


def test_ordered_by_day(store):
    rows = store.user_daily_series("alice", "2026-09", "acme")
    days = [r["day"] for r in rows]
    assert days == sorted(days)


def test_unknown_user_gets_all_zeros(store):
    rows = store.user_daily_series("nobody", "2026-09", "acme")
    assert len(rows) == 30
    assert all(r["credits"] == 0.0 and r["interactions"] == 0 for r in rows)


def test_scope_none_matches_all(store):
    rows = store.user_daily_series("bob", "2026-09", None)
    third = next(r for r in rows if r["day"] == "2026-09-03")
    assert third["credits"] == pytest.approx(50.0)


def test_scope_filters(store):
    rows = store.user_daily_series("bob", "2026-09", "other")
    assert all(r["credits"] == 0.0 for r in rows)
