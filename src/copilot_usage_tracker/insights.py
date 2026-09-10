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


def forecast_month_end(
    store: UsageStore, month: str, scope: str | None,
    book: PriceBook, seats: int,
) -> dict:
    """Project month-end credits and cost from the daily run rate.

    Uses days that actually have collected data (not the calendar day),
    so a mid-month view and a partial backfill both extrapolate sanely.
    """
    import calendar

    year, mon = (int(p) for p in month.split("-", 1))
    days_in_month = calendar.monthrange(year, mon)[1]
    daily = store.daily_series(month, scope)
    days_elapsed = len(daily)
    credits_so_far = sum(r["ai_credits_used"] for r in daily)
    run_rate = credits_so_far / days_elapsed if days_elapsed else 0.0
    projected_credits = run_rate * days_in_month
    cost = book.monthly_cost(seats, projected_credits)
    return {
        "month": month,
        "scope": scope,
        "days_elapsed": days_elapsed,
        "days_in_month": days_in_month,
        "daily_run_rate": round(run_rate, 2),
        "credits_so_far": round(credits_so_far, 2),
        "projected_credits": round(projected_credits, 2),
        "projected_total_usd": cost["total_cost_usd"],
        "projected_overage_usd": cost["overage_cost_usd"],
        "projected_utilization": cost["utilization"],
    }


def engagement_summary(
    store: UsageStore, month: str, scope: str | None
) -> dict:
    """How much value users get: interactions, lines added, engagement rate."""
    totals = store.engagement_totals(month, scope)
    active = store.monthly_active_users(month, scope)
    engaged = store.monthly_engaged_users(month, scope)
    return {
        "month": month,
        "scope": scope,
        "interactions": totals["interactions"],
        "loc_added": totals["loc_added"],
        "active_users": active,
        "engaged_users": engaged,
        "engagement_rate": (engaged / active) if active else 0.0,
        "interactions_per_engaged_user": (
            round(totals["interactions"] / engaged, 1) if engaged else 0.0
        ),
        "loc_per_engaged_user": (
            round(totals["loc_added"] / engaged, 1) if engaged else 0.0
        ),
    }


def engagement_daily_series(
    store: UsageStore, month: str, scope: str | None
) -> list[dict]:
    """Per-day engagement rows for charts."""
    return [
        {
            "day": r["day"],
            "interactions": r["interactions"],
            "loc_added": r["loc_added"],
            "engaged_users": r["engaged_users"],
            "active_users": r["active_users"],
        }
        for r in store.daily_engagement(month, scope)
    ]


def dormant_seats(
    store: UsageStore, days: int, scope: str | None,
    book: PriceBook, today: str | None = None,
) -> dict:
    """Seats that show no Copilot usage in the trailing `days` days.

    Each dormant seat is a candidate for license reclamation; savings use
    the plan's per-seat price.
    """
    users = store.dormant_users(days=days, scope=scope, today=today)
    savings = round(len(users) * book.seat_price_monthly, 2)
    return {
        "days": days,
        "scope": scope,
        "dormant_count": len(users),
        "potential_monthly_savings_usd": savings,
        "seat_price_usd": book.seat_price_monthly,
        "users": [
            {
                "user": r["user_login"],
                "last_active_day": r["last_active_day"] or "never",
            }
            for r in users
        ],
    }
