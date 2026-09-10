"""Tests for store retention purging."""

import pytest

from copilot_usage_tracker.store import UsageStore


@pytest.fixture()
def store(tmp_path):
    s = UsageStore(tmp_path / "test.db")
    # old rows (way outside any sane retention window)
    s.upsert_user_day("2020-01-01", "acme", 1, user_login="alice", ai_credits_used=10)
    s.upsert_scope_day("2020-01-01", "acme", "enterprise", ai_credits_used=10)
    s.upsert_team_day("2020-01-01", "acme", 42, slug="frontend", ai_credits_used=10)
    s.upsert_model_day("2020-01-01", "acme", "model-x", input_tokens=100)
    # recent rows (today-ish via far-future date to survive any cutoff)
    s.upsert_user_day("2099-01-01", "acme", 2, user_login="bob", ai_credits_used=20)
    s.upsert_scope_day("2099-01-01", "acme", "enterprise", ai_credits_used=20)
    s.upsert_team_day("2099-01-01", "acme", 43, slug="backend", ai_credits_used=20)
    s.upsert_model_day("2099-01-01", "acme", "model-y", input_tokens=200)
    yield s
    s.close()


def test_purge_older_than_removes_old_only(store):
    counts = store.purge_older_than(30)
    assert counts == {"user_daily": 1, "scope_daily": 1,
                      "team_daily": 1, "model_daily": 1}
    # recent rows survive
    assert store.monthly_credits("2099-01") == 20
    assert store.monthly_credits("2020-01") == 0
    assert store.top_users("2099-01")[0]["user_login"] == "bob"


def test_purge_zero_days_keeps_nothing_old():
    # days=0 -> cutoff is today; the 2020 rows are still older
    import tempfile
    from pathlib import Path

    with tempfile.TemporaryDirectory() as d:
        s = UsageStore(Path(d) / "t.db")
        s.upsert_scope_day("2020-06-01", "acme", "enterprise", ai_credits_used=5)
        counts = s.purge_older_than(0)
        assert counts["scope_daily"] == 1
        s.close()


def _engagement_store(tmp_path):
    s = UsageStore(tmp_path / "eng.db")
    s.upsert_user_day("2026-09-01", "acme", 1, user_login="alice",
                      ai_credits_used=900, interactions=10, loc_added=50)
    s.upsert_user_day("2026-09-01", "acme", 2, user_login="bob",
                      ai_credits_used=100, interactions=5, loc_added=10)
    s.upsert_user_day("2026-09-02", "acme", 1, user_login="alice",
                      ai_credits_used=0, interactions=0, loc_added=0)
    return s


def test_daily_engagement(tmp_path):
    store = _engagement_store(tmp_path)
    try:
        rows = store.daily_engagement("2026-09", "acme")
        assert len(rows) == 2
        assert rows[0]["day"] == "2026-09-01"
        assert rows[0]["interactions"] == 15
        assert rows[0]["loc_added"] == 60
        assert rows[0]["engaged_users"] == 2
        assert rows[0]["active_users"] == 2
        assert rows[1]["engaged_users"] == 0
    finally:
        store.close()


def test_monthly_engaged_users(tmp_path):
    store = _engagement_store(tmp_path)
    try:
        assert store.monthly_engaged_users("2026-09", "acme") == 2
        assert store.monthly_engaged_users("2026-10", "acme") == 0
    finally:
        store.close()


def test_dormant_users(tmp_path):
    store = _engagement_store(tmp_path)
    try:
        # Last activity 2026-09-01; 30-day window from 09-02: nobody dormant.
        assert store.dormant_users(30, "acme", today="2026-09-02") == []
        # Far in the future both are dormant, alice last active 09-01
        # (the 09-02 row has 0 credits).
        dormant = store.dormant_users(30, "acme", today="2026-11-01")
        assert {r["user_login"] for r in dormant} == {"alice", "bob"}
        assert all(r["last_active_day"] == "2026-09-01" for r in dormant)
    finally:
        store.close()
