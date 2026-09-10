"""Tests for the AI-credit cost model and token estimation."""

from copilot_usage_tracker.tokens import (
    CREDIT_USD,
    PriceBook,
    credits_to_usd,
    estimate_tokens_from_lines,
)


def test_credit_conversion():
    assert CREDIT_USD == 0.01
    assert credits_to_usd(1900) == 19.0
    assert credits_to_usd(0) == 0.0


def test_price_book_defaults():
    business = PriceBook.for_plan("business")
    assert business.seat_price_monthly == 19.0
    assert business.included_credits_per_seat == 1900.0
    enterprise = PriceBook.for_plan("enterprise")
    assert enterprise.seat_price_monthly == 39.0
    assert enterprise.included_credits_per_seat == 3900.0


def test_monthly_cost_within_allowance():
    book = PriceBook.for_plan("business", overage_allowed=True)
    result = book.monthly_cost(seats=10, credits_used=5_000)
    assert result["seat_cost_usd"] == 190.0
    assert result["overage_credits"] == 0
    assert result["overage_cost_usd"] == 0.0
    assert result["total_cost_usd"] == 190.0


def test_monthly_cost_overage_billed():
    book = PriceBook.for_plan("business", overage_allowed=True)
    # 10 seats -> 19,000 pooled credits; use 20,000 -> 1,000 overage = $10
    result = book.monthly_cost(seats=10, credits_used=20_000)
    assert result["overage_credits"] == 1000
    assert result["overage_cost_usd"] == 10.0
    assert result["total_cost_usd"] == 200.0


def test_monthly_cost_overage_capped():
    book = PriceBook.for_plan("business", overage_allowed=False)
    result = book.monthly_cost(seats=10, credits_used=20_000)
    assert result["overage_cost_usd"] == 0.0
    assert result["total_cost_usd"] == 190.0


def test_estimate_tokens_from_lines():
    assert estimate_tokens_from_lines(100) == 1000
    assert estimate_tokens_from_lines(0) == 0
    assert estimate_tokens_from_lines(-5) == 0
    assert estimate_tokens_from_lines(100, chars_per_token=2.0) == 2000
