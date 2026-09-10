"""Pure aggregation helpers shared by the CLI and the dashboard.

These functions take a UsageStore and return plain dicts/lists, so they are
trivially testable and the Streamlit app stays a thin presentation layer.
"""

from __future__ import annotations

from .store import UsageStore
from .tokens import PriceBook, credits_to_usd


def monthly_kpis(
    store: UsageStore, month: str, scope: str | None,
    book: PriceBook, seats: int,
) -> dict:
    """Headline numbers for a month: credits, dollars, utilization."""
    credits = store.monthly_credits(month, scope)
    cost = book.monthly_cost(seats, credits)
    token_totals = store.model_token_totals(month, scope)
    return {
        "month": month,
        "scope": scope,
        "credits_used": round(credits, 2),
        "credits_usd": round(credits_to_usd(credits), 2),
        "seat_cost_usd": cost["seat_cost_usd"],
        "overage_cost_usd": cost["overage_cost_usd"],
        "total_cost_usd": cost["total_cost_usd"],
        "utilization": cost["utilization"],
        "input_tokens": token_totals["input_tokens"],
        "output_tokens": token_totals["output_tokens"],
        "active_users": store.monthly_active_users(month, scope),
    }


def daily_spend_series(store: UsageStore, month: str, scope: str | None) -> list[dict]:
    """Per-day credits and dollars for time-series charts."""
    return [
        {
            "day": r["day"],
            "credits": r["ai_credits_used"],
            "usd": round(credits_to_usd(r["ai_credits_used"]), 2),
        }
        for r in store.daily_series(month, scope)
    ]


def team_leaderboard(store: UsageStore, month: str, scope: str | None) -> list[dict]:
    """Per-team credit consumption, richest first, with dollar conversion."""
    rows = []
    for r in store.team_totals(month, scope):
        rows.append(
            {
                "team": r["slug"],
                "active_users": r["active_users"],
                "credits": round(r["ai_credits_used"], 2),
                "usd": round(credits_to_usd(r["ai_credits_used"]), 2),
            }
        )
    return rows


def top_users_with_cost(
    store: UsageStore, month: str, scope: str | None, limit: int = 20
) -> list[dict]:
    """Top credit consumers with dollar costs attached."""
    return [
        {
            "user": r["user_login"],
            "credits": round(r["credits"], 2),
            "usd": round(credits_to_usd(r["credits"]), 2),
        }
        for r in store.top_users(month, limit, scope)
    ]


def model_breakdown(store: UsageStore, month: str, scope: str | None) -> list[dict]:
    """Per-model input/output/cache tokens and billed dollars."""
    return [
        {
            "model": r["model"],
            "input_tokens": r["input_tokens"],
            "output_tokens": r["output_tokens"],
            "cache_read_tokens": r["cache_read_tokens"],
            "cache_write_tokens": r["cache_write_tokens"],
            "gross_usd": round(r["gross_amount_usd"], 2),
            "net_usd": round(r["net_amount_usd"], 2),
        }
        for r in store.model_breakdown(month, scope)
    ]
