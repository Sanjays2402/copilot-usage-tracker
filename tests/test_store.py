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
