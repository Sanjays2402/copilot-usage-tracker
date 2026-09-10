"""Tests for the dashboard aggregation helpers."""

import pytest

from copilot_usage_tracker.insights import (
    daily_spend_series,
    dormant_seats,
    engagement_daily_series,
    engagement_summary,
    forecast_month_end,
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


def test_forecast_month_end(store):
    book = PriceBook.for_plan("business")
    fc = forecast_month_end(store, "2026-09", "acme", book, seats=10)
    # 2 days of data: 1000 + 500 = 1500 -> run rate 750/day over 30 days
    assert fc["days_elapsed"] == 2
    assert fc["days_in_month"] == 30
    assert fc["daily_run_rate"] == 750.0
    assert fc["projected_credits"] == 22500.0
    # 10 seats * $19 = $190 seat cost; 22500 - 19000 allowance = 3500 overage
    # overage not allowed by default -> cost is seats only
    assert fc["projected_total_usd"] == 190.00


def test_forecast_no_data(store):
    book = PriceBook.for_plan("business")
    fc = forecast_month_end(store, "2026-10", "acme", book, seats=10)
    assert fc["days_elapsed"] == 0
    assert fc["projected_credits"] == 0.0
    assert fc["projected_total_usd"] == 190.00


def test_engagement_summary(store):
    eng = engagement_summary(store, "2026-09", "acme")
    assert eng["interactions"] == 15
    assert eng["loc_added"] == 60
    assert eng["active_users"] == 2
    assert eng["engaged_users"] == 2
    assert eng["engagement_rate"] == 1.0
    assert eng["interactions_per_engaged_user"] == 7.5
    assert eng["loc_per_engaged_user"] == 30.0


def test_engagement_daily_series(store):
    series = engagement_daily_series(store, "2026-09", "acme")
    assert len(series) == 1
    assert series[0]["day"] == "2026-09-01"
    assert series[0]["interactions"] == 15
    assert series[0]["engaged_users"] == 2


def test_dormant_seats(store):
    # Everyone in the fixture was active 2026-09-01; with today 2026-09-02
    # and a 30-day window nobody is dormant.
    book = PriceBook.for_plan("business")
    report = dormant_seats(store, 30, "acme", book, today="2026-09-02")
    assert report["dormant_count"] == 0
    assert report["potential_monthly_savings_usd"] == 0.0
    # With a 1-day window both users are dormant: last active 09-01,
    # cutoff is 09-01 -> strictly older required.
    report = dormant_seats(store, 0, "acme", book, today="2026-09-02")
    assert report["dormant_count"] == 2
    assert report["potential_monthly_savings_usd"] == 38.0
    assert report["seat_price_usd"] == 19.0
    logins = {u["user"] for u in report["users"]}
    assert logins == {"alice", "bob"}
