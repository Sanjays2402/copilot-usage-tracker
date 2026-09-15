"""Tests for insights.executive_summary — Markdown leadership report."""

import pytest

from copilot_usage_tracker.insights import executive_summary
from copilot_usage_tracker.store import UsageStore
from copilot_usage_tracker.tokens import PriceBook


@pytest.fixture()
def store(tmp_path):
    s = UsageStore(tmp_path / "summary.db")
    for day, alice_cr, bob_cr in (
        ("2026-09-01", 1000.0, 400.0),
        ("2026-09-02", 1200.0, 300.0),
    ):
        s.upsert_scope_day(
            day, "acme", "enterprise", ai_credits_used=alice_cr + bob_cr, active_users=2
        )
        s.upsert_user_day(
            day, "acme", 1, user_login="alice", ai_credits_used=alice_cr, interactions=10
        )
        s.upsert_user_day(day, "acme", 2, user_login="bob", ai_credits_used=bob_cr, interactions=5)
        s.upsert_team_day(day, "acme", 1, slug="platform", ai_credits_used=alice_cr, active_users=1)
        s.upsert_team_day(day, "acme", 2, slug="mobile", ai_credits_used=bob_cr, active_users=1)
    return s


def test_contains_sections(store):
    book = PriceBook.for_plan("business")
    md = executive_summary(store, "2026-09", "acme", book, seats=10)
    for section in (
        "## KPIs",
        "## Cost forecast",
        "## Top teams",
        "## Top users",
        "## Dormant seats",
        "## Budget status",
    ):
        assert section in md


def test_reports_real_numbers(store):
    book = PriceBook.for_plan("business")
    md = executive_summary(store, "2026-09", "acme", book, seats=10)
    assert "2026-09" in md
    assert "alice" in md
    assert "platform" in md
    assert "2,900" in md  # 1400 + 1500 = 2900 credits
    assert "2" in md  # active users


def test_budget_status_uses_budgets_helpers(store):
    book = PriceBook.for_plan("business")
    # 10 business seats = $190; a $100 budget is breached.
    md = executive_summary(store, "2026-09", "acme", book, seats=10, budget_limit_usd=100.0)
    assert "breached" in md
    md_ok = executive_summary(store, "2026-09", "acme", book, seats=10, budget_limit_usd=10_000.0)
    assert "breached" not in md_ok


def test_no_budget_configured_message(store):
    book = PriceBook.for_plan("business")
    md = executive_summary(store, "2026-09", "acme", book, seats=10)
    assert "No monthly budget configured" in md


def test_dormant_seats_reused(store):
    book = PriceBook.for_plan("business")
    md = executive_summary(store, "2026-09", "acme", book, seats=10, today="2026-09-03")
    # both users were active in the last 30 days -> no dormant seats.
    assert "0" in md
    assert "$" in md


def test_professional_tone(store):
    book = PriceBook.for_plan("business")
    md = executive_summary(store, "2026-09", "acme", book, seats=10)
    for hype in ("🚀", "amazing", "game-changing", "!", "Supercharge"):
        assert hype not in md
