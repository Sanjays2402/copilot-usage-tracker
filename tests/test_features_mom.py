"""Tests for insights.month_over_month — KPI deltas vs previous month."""

import pytest

from copilot_usage_tracker.insights import month_over_month
from copilot_usage_tracker.store import UsageStore
from copilot_usage_tracker.tokens import PriceBook


@pytest.fixture()
def store(tmp_path):
    s = UsageStore(tmp_path / "mom.db")
    # August: 2 users, 3000 credits across 2 scope rows.
    s.upsert_scope_day("2026-08-31", "acme", "enterprise", ai_credits_used=2000, active_users=2)
    s.upsert_scope_day("2026-08-30", "acme", "enterprise", ai_credits_used=1000, active_users=1)
    s.upsert_user_day("2026-08-31", "acme", 1, user_login="alice", ai_credits_used=2000)
    s.upsert_user_day("2026-08-31", "acme", 2, user_login="bob", ai_credits_used=1000)
    # September: 3 users, 4000 credits.
    s.upsert_scope_day("2026-09-05", "acme", "enterprise", ai_credits_used=4000, active_users=3)
    s.upsert_user_day("2026-09-05", "acme", 1, user_login="alice", ai_credits_used=2000)
    s.upsert_user_day("2026-09-05", "acme", 2, user_login="bob", ai_credits_used=1000)
    s.upsert_user_day("2026-09-05", "acme", 3, user_login="carol", ai_credits_used=1000)
    return s


def test_credit_and_user_deltas(store):
    book = PriceBook.for_plan("business", overage_allowed=True)
    mom = month_over_month(store, "2026-09", "acme", book, seats=0)
    assert mom["credits"]["current"] == pytest.approx(4000.0)
    assert mom["credits"]["previous"] == pytest.approx(3000.0)
    assert mom["credits"]["delta"] == pytest.approx(1000.0)
    assert mom["active_users"]["current"] == 3
    assert mom["active_users"]["previous"] == 2
    assert mom["active_users"]["delta"] == 1


def test_cost_delta_uses_pricebook(store):
    book = PriceBook.for_plan("business", overage_allowed=True)
    mom = month_over_month(store, "2026-09", "acme", book, seats=10)
    # 10 business seats = $190 seat cost; 4000 credits of 19,000 allowance.
    assert mom["total_cost"]["current"] == pytest.approx(190.0)
    assert mom["total_cost"]["previous"] == pytest.approx(190.0)
    assert mom["total_cost"]["delta"] == pytest.approx(0.0)


def test_missing_previous_month_treated_as_zero(tmp_path):
    s = UsageStore(tmp_path / "one.db")
    s.upsert_scope_day("2026-09-05", "acme", "enterprise", ai_credits_used=4000, active_users=3)
    book = PriceBook.for_plan("business")
    mom = month_over_month(s, "2026-09", "acme", book, seats=0)
    assert mom["credits"]["previous"] == 0
    assert mom["credits"]["delta"] == pytest.approx(4000.0)
    assert mom["active_users"]["previous"] == 0


def test_january_rolls_back_to_december(tmp_path):
    s = UsageStore(tmp_path / "jan.db")
    s.upsert_scope_day("2025-12-15", "acme", "enterprise", ai_credits_used=700, active_users=1)
    s.upsert_user_day("2025-12-15", "acme", 1, user_login="alice", ai_credits_used=700)
    s.upsert_scope_day("2026-01-10", "acme", "enterprise", ai_credits_used=900, active_users=2)
    s.upsert_user_day("2026-01-10", "acme", 1, user_login="alice", ai_credits_used=700)
    s.upsert_user_day("2026-01-10", "acme", 2, user_login="bob", ai_credits_used=200)
    book = PriceBook.for_plan("business")
    mom = month_over_month(s, "2026-01", "acme", book, seats=0)
    assert mom["credits"]["current"] == pytest.approx(900.0)
    assert mom["credits"]["previous"] == pytest.approx(700.0)
    assert mom["credits"]["delta"] == pytest.approx(200.0)
    assert mom["active_users"]["previous"] == 1
