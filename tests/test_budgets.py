"""Tests for budgets and alerts."""

from copilot_usage_tracker.budgets import Budget, check_budgets


def test_budget_ok():
    assert Budget(scope="acme", limit_usd=1000, spent_usd=100).status() == "ok"


def test_budget_warning_at_threshold():
    assert Budget(scope="acme", limit_usd=1000, spent_usd=800).status() == "warning"


def test_budget_breached():
    assert Budget(scope="acme", limit_usd=1000, spent_usd=1200).status() == "breached"


def test_check_budgets_only_alerts():
    budgets = [
        Budget(scope="ok-team", limit_usd=1000, spent_usd=100),
        Budget(scope="hot-team", limit_usd=1000, spent_usd=950),
    ]
    alerts = check_budgets(budgets)
    assert len(alerts) == 1
    assert alerts[0].scope == "hot-team"
    assert alerts[0].status == "warning"
    assert "hot-team" in alerts[0].message
