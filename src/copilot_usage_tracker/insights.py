"""Pure aggregation helpers shared by the CLI and the dashboard.

These functions take a UsageStore and return plain dicts/lists, so they are
trivially testable and the Streamlit app stays a thin presentation layer.
"""

from __future__ import annotations

from .budgets import Budget, check_budgets
from .store import UsageStore
from .tokens import PriceBook, credits_to_usd


def monthly_kpis(
    store: UsageStore,
    month: str,
    scope: str | None,
    book: PriceBook,
    seats: int,
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
    store: UsageStore,
    month: str,
    scope: str | None,
    book: PriceBook,
    seats: int,
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


def engagement_summary(store: UsageStore, month: str, scope: str | None) -> dict:
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
        "loc_per_engaged_user": (round(totals["loc_added"] / engaged, 1) if engaged else 0.0),
    }


def engagement_daily_series(store: UsageStore, month: str, scope: str | None) -> list[dict]:
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
    store: UsageStore,
    days: int,
    scope: str | None,
    book: PriceBook,
    today: str | None = None,
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


def spike_alerts(
    store: UsageStore,
    month: str,
    scope: str | None,
    min_history_days: int = 7,
    factor: float = 3.0,
    min_credits: float = 50.0,
) -> list[dict]:
    """Flag users whose latest day's credits dwarf their recent history.

    A user qualifies when they have at least ``min_history_days`` daily rows
    in the month, their latest day's credits are at least ``min_credits``,
    and that day is >= ``factor`` times their trailing mean. The trailing
    mean is computed over the days *before* the latest day (so a spike day
    does not inflate its own baseline). Users are sorted by spike multiple,
    largest first.
    """
    q = "FROM user_daily WHERE day LIKE ?"
    args: list = [f"{month}%"]
    if scope:
        q += " AND scope = ?"
        args.append(scope)
    rows = store.conn.execute(
        f"SELECT user_login, day, SUM(ai_credits_used) AS credits {q} "
        "GROUP BY user_login, day ORDER BY user_login, day",
        args,
    ).fetchall()
    per_user: dict[str, list[tuple[str, float]]] = {}
    for r in rows:
        per_user.setdefault(r["user_login"], []).append((r["day"], float(r["credits"])))
    alerts = []
    for login, days in per_user.items():
        if len(days) < min_history_days:
            continue
        latest_day, latest_credits = days[-1]
        if latest_credits < min_credits:
            continue
        history = [c for _, c in days[:-1]]
        trailing_avg = sum(history) / len(history)
        if trailing_avg > 0:
            multiple = latest_credits / trailing_avg
        else:
            # No prior usage: any qualifying latest day is an infinite spike.
            multiple = float("inf") if latest_credits > 0 else 0.0
        if latest_credits >= factor * trailing_avg:
            alerts.append(
                {
                    "user": login,
                    "latest_day": latest_day,
                    "latest_credits": round(latest_credits, 2),
                    "trailing_avg": round(trailing_avg, 2),
                    "multiple": (round(multiple, 2) if multiple != float("inf") else multiple),
                }
            )
    alerts.sort(key=lambda a: a["multiple"], reverse=True)
    return alerts


def _previous_month(month: str) -> str:
    """Calendar month before ``month`` ("YYYY-MM"), handling year rollover."""
    year, mon = (int(p) for p in month.split("-", 1))
    if mon == 1:
        return f"{year - 1}-12"
    return f"{year}-{mon - 1:02d}"


def _month_kpis_for_mom(
    store: UsageStore,
    month: str,
    scope: str | None,
    book: PriceBook,
    seats: int,
) -> dict:
    credits = store.monthly_credits(month, scope)
    return {
        "credits": round(credits, 2),
        "total_cost": book.monthly_cost(seats, credits)["total_cost_usd"],
        "active_users": store.monthly_active_users(month, scope),
    }


def month_over_month(
    store: UsageStore,
    month: str,
    scope: str | None,
    book: PriceBook,
    seats: int,
) -> dict:
    """Compare a month's KPIs against the previous calendar month.

    Months with no data are treated as zeros. Returns one
    ``{"current", "previous", "delta"}`` entry each for credits, total
    cost (via the PriceBook), and active users.
    """
    prev = _previous_month(month)
    current = _month_kpis_for_mom(store, month, scope, book, seats)
    previous = _month_kpis_for_mom(store, prev, scope, book, seats)
    out: dict = {"month": month, "previous_month": prev}
    for key in ("credits", "total_cost", "active_users"):
        out[key] = {
            "current": current[key],
            "previous": previous[key],
            "delta": round(current[key] - previous[key], 2),
        }
    return out


def executive_summary(
    store: UsageStore,
    month: str,
    scope: str | None,
    book: PriceBook,
    seats: int,
    budget_limit_usd: float | None = None,
    today: str | None = None,
) -> str:
    """Render a leadership-ready Markdown report for the month.

    Reuses the same helpers as the dashboard (KPIs, forecast, dormant
    seats, budgets) so the numbers here always match the GUI.
    """
    kpis = monthly_kpis(store, month, scope, book, seats)
    forecast = forecast_month_end(store, month, scope, book, seats)
    teams = team_leaderboard(store, month, scope)[:5]
    users = top_users_with_cost(store, month, scope, limit=5)
    seats_info = dormant_seats(store, 30, scope, book, today=today)

    lines = [
        f"# Copilot usage — executive summary ({month})",
        "",
        f"Scope: {scope or 'all'} · Plan: {book.plan} · Granted seats: {seats}",
        "",
        "## KPIs",
        "",
        f"- Credits used: {kpis['credits_used']:,.0f}",
        f"- Total cost: ${kpis['total_cost_usd']:,.2f}",
        f"- Active users: {kpis['active_users']:,}",
        f"- Allowance utilization: {kpis['utilization']:.1%}",
        "",
        "## Cost forecast",
        "",
        f"- Daily run rate: {forecast['daily_run_rate']:,.0f} credits/day",
        f"- Projected month-end credits: {forecast['projected_credits']:,.0f}",
        f"- Projected month-end cost: ${forecast['projected_total_usd']:,.2f}",
        (
            f"- Projected overage: ${forecast['projected_overage_usd']:,.2f} "
            f"(data coverage: {forecast['days_elapsed']}/"
            f"{forecast['days_in_month']} days)"
        ),
        "",
        "## Top teams",
        "",
    ]
    if teams:
        for i, t in enumerate(teams, 1):
            lines.append(
                f"{i}. {t['team']} — {t['credits']:,.0f} credits "
                f"(${t['usd']:,.2f}, {t['active_users']} users)"
            )
    else:
        lines.append("- No team data for this month.")
    lines += ["", "## Top users", ""]
    if users:
        for i, u in enumerate(users, 1):
            lines.append(f"{i}. {u['user']} — {u['credits']:,.0f} credits (${u['usd']:,.2f})")
    else:
        lines.append("- No user data for this month.")
    lines += [
        "",
        "## Dormant seats",
        "",
        f"- Dormant seats (no usage in 30 days): {seats_info['dormant_count']:,}",
        (
            "- Potential monthly savings from reclamation: "
            f"${seats_info['potential_monthly_savings_usd']:,.2f}"
        ),
        "",
        "## Budget status",
        "",
    ]
    if budget_limit_usd and budget_limit_usd > 0:
        budget = Budget(
            scope=scope or "all", limit_usd=budget_limit_usd, spent_usd=kpis["total_cost_usd"]
        )
        alerts = check_budgets([budget])
        lines.append(
            f"- Spent ${budget.spent_usd:,.2f} of "
            f"${budget.limit_usd:,.2f} ({budget.utilization:.0%} of budget)."
        )
        if alerts:
            lines.append(f"- Status: {alerts[0].status.upper()} — {alerts[0].message}")
        else:
            lines.append("- Status: within budget.")
    else:
        lines.append("- No monthly budget configured.")
    lines += [
        "",
        (
            "_Generated locally by copilot-usage-tracker; figures are derived "
            "from collected GitHub Copilot usage data._"
        ),
        "",
    ]
    return "\n".join(lines)
