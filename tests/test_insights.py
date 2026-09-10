"""Tests for the dashboard aggregation helpers."""

import pytest

from copilot_usage_tracker.insights import (
    daily_spend_series,
    model_breakdown,
    monthly_kpis,
    team_leaderboard,
    top_users_with_cost,
)
from copilot_usage_tracker.store import UsageStore
from copilot_usage_tracker.tokens import PriceBook


@pytest.fixture()
def store(tmp_path):
    s = UsageStore(tmp_path / "test.db")
    s.upsert_scope_day("2026-09-01", "acme", "enterprise",
                       ai_credits_used=1000, active_users=2)
    s.upsert_scope_day("2026-09-02", "acme", "enterprise",
                       ai_credits_used=500, active_users=1)
    s.upsert_user_day("2026-09-01", "acme", 1, user_login="alice",
                      ai_credits_used=900, interactions=10, loc_added=50)
    s.upsert_user_day("2026-09-01", "acme", 2, user_login="bob",
                      ai_credits_used=100, interactions=5, loc_added=10)
    s.upsert_team_day("2026-09-01", "acme", 42, slug="frontend",
                      ai_credits_used=900, active_users=1)
    s.upsert_team_day("2026-09-01", "acme", 43, slug="backend",
                      ai_credits_used=100, active_users=1)
    s.upsert_model_day("2026-09-01", "acme", "claude-sonnet-4.5",
                       user_login="alice", input_tokens=1_200_000,
                       output_tokens=300_000, cache_read_tokens=50_000,
                       gross_amount_usd=18.50, net_amount_usd=8.50)
    s.upsert_model_day("2026-09-01", "acme", "gpt-5-mini",
                       user_login="bob", input_tokens=800_000,
                       output_tokens=200_000,
                       gross_amount_usd=12.00, net_amount_usd=0.00)
    yield s
    s.close()


def test_monthly_kpis(store):
    kpis = monthly_kpis(store, "2026-09", "acme",
                        PriceBook.for_plan("business"), seats=10)
    assert kpis["credits_used"] == 1500
    assert kpis["credits_usd"] == 15.00
    assert kpis["seat_cost_usd"] == 190.00
    assert kpis["overage_cost_usd"] == 0.0  # within pooled allowance
    assert kpis["total_cost_usd"] == 190.00
    assert kpis["input_tokens"] == 2_000_000
    assert kpis["output_tokens"] == 500_000
    assert kpis["active_users"] == 2


def test_monthly_kpis_overage(store):
    book = PriceBook.for_plan("business", overage_allowed=True)
    kpis = monthly_kpis(store, "2026-09", "acme", book, seats=0)
    # 0 seats -> 0 allowance -> all 1500 credits are overage = $15
    assert kpis["overage_cost_usd"] == 15.00
    assert kpis["total_cost_usd"] == 15.00


def test_daily_spend_series(store):
    series = daily_spend_series(store, "2026-09", "acme")
    assert [d["day"] for d in series] == ["2026-09-01", "2026-09-02"]
    assert series[0]["credits"] == 1000
    assert series[0]["usd"] == 10.00


def test_team_leaderboard(store):
    board = team_leaderboard(store, "2026-09", "acme")
    assert [t["team"] for t in board] == ["frontend", "backend"]
    assert board[0]["credits"] == 900
    assert board[0]["usd"] == 9.00


def test_top_users_with_cost(store):
    top = top_users_with_cost(store, "2026-09", "acme")
    assert [u["user"] for u in top] == ["alice", "bob"]
    assert top[0]["usd"] == 9.00


def test_model_breakdown(store):
    models = model_breakdown(store, "2026-09", "acme")
    assert [m["model"] for m in models] == ["claude-sonnet-4.5", "gpt-5-mini"]
    assert models[0]["input_tokens"] == 1_200_000
    assert models[0]["output_tokens"] == 300_000
    assert models[0]["cache_read_tokens"] == 50_000
    assert models[0]["net_usd"] == 8.50
