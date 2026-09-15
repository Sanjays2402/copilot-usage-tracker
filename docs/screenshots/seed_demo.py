"""Seed a demo database with fictional sample data for screenshots.

Run:  COPILOT_DB=docs/screenshots/demo.db python docs/screenshots/seed_demo.py
Then: COPILOT_DB=docs/screenshots/demo.db streamlit run dashboard/app.py

Covers the newest dashboard capabilities so every screenshot shows them:
- a latest-day usage spike (demo-alice: ~100 credits/day, then 500 on
  2026-09-14) that renders the "Unusual activity" section;
- August + September data so the month-over-month KPI deltas are non-zero;
- two teams and six users so the Teams leaderboard, top-5 summary lists,
  and the Users-tab drill-down selectbox all populate;
- a dormant seat (demo-grace, last active 2026-08-01) for the Seats tab.

All logins, teams, and numbers are fictional.
"""

from __future__ import annotations

import os
import random
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))

from copilot_usage_tracker.store import UsageStore

SCOPE = "acme-corp"
# August covers the same 14 calendar days as September (so the demo
# month-over-month deltas read as growth, not a partial-month artifact).
AUG_DAYS = [f"2026-08-{d:02d}" for d in range(1, 15)]
SEP_DAYS = [f"2026-09-{d:02d}" for d in range(1, 15)]  # through 2026-09-14
SPIKE_DAY = SEP_DAYS[-1]

# (user_id, login, team_id, team_slug, september base credits/day)
USERS = [
    (101, "demo-alice", 1, "platform", 100.0),  # spike user
    (102, "demo-bob", 1, "platform", 210.0),
    (103, "demo-carol", 1, "platform", 150.0),
    (104, "demo-dave", 2, "mobile", 260.0),
    (105, "demo-erin", 2, "mobile", 180.0),
    (106, "demo-frank", 2, "mobile", 90.0),
]

MODELS = [
    # (model, input_share, output_share)
    ("gpt-5", 0.55, 0.30),
    ("claude-sonnet-4.5", 0.30, 0.45),
    ("gpt-5-mini", 0.15, 0.25),
]

# September is a growth month: August runs at 65% of September's base so the
# Overview KPI deltas vs the previous month are non-zero.
AUGUST_RATIO = 0.65


def is_weekend(day: str) -> bool:
    year, month, dom = (int(p) for p in day.split("-"))
    import datetime

    return datetime.date(year, month, dom).weekday() >= 5


def user_credits(login: str, base: float, day: str, august: bool) -> float:
    """Deterministic-ish daily credits for a demo user."""
    if login == "demo-alice" and not august:
        # Steady baseline all September, then one big spike day.
        if day == SPIKE_DAY:
            return 500.0
        return round(100 * random.uniform(0.92, 1.08), 1)
    credits = base * (AUGUST_RATIO if august else 1.0)
    credits *= random.uniform(0.7, 1.3)
    if is_weekend(day):
        credits *= 0.15
    return round(max(credits, 1.0), 1)


def seed_day(store: UsageStore, day: str, august: bool, with_models: bool) -> None:
    team_credits = {1: 0.0, 2: 0.0}
    team_users = {1: set(), 2: set()}
    scope_credits = 0.0
    for user_id, login, team_id, _slug, base in USERS:
        credits = user_credits(login, base, day, august)
        interactions = int(credits * random.uniform(1.5, 2.5))
        store.upsert_user_day(
            day,
            SCOPE,
            user_id,
            user_login=login,
            ai_credits_used=credits,
            interactions=interactions,
            loc_added=int(credits * random.uniform(8, 14)),
        )
        scope_credits += credits
        team_credits[team_id] += credits
        team_users[team_id].add(login)
        if with_models:
            for model, in_share, out_share in MODELS:
                in_tok = int(credits * 1000 * in_share * random.uniform(0.8, 1.2))
                out_tok = int(credits * 1000 * out_share * random.uniform(0.8, 1.2))
                gross = round((in_tok + out_tok * 3) / 1000 * 0.004, 4)
                store.upsert_model_day(
                    day,
                    SCOPE,
                    model,
                    user_login=login,
                    input_tokens=in_tok,
                    output_tokens=out_tok,
                    cache_read_tokens=int(in_tok * random.uniform(0.3, 0.6)),
                    cache_write_tokens=int(in_tok * 0.05),
                    gross_amount_usd=gross,
                    net_amount_usd=round(gross * 0.9, 4),
                )
    for team_id, slug in ((1, "platform"), (2, "mobile")):
        store.upsert_team_day(
            day,
            SCOPE,
            team_id,
            slug=slug,
            ai_credits_used=round(team_credits[team_id], 1),
            active_users=len(team_users[team_id]),
        )
    store.upsert_scope_day(
        day,
        SCOPE,
        "org",
        ai_credits_used=round(scope_credits, 1),
        billed_usd=round(scope_credits * 0.01, 2),
        active_users=sum(len(u) for u in team_users.values()),
    )


def main() -> None:
    random.seed(42)
    db_path = os.environ.get("COPILOT_DB", "docs/screenshots/demo.db")
    if os.path.exists(db_path):
        os.remove(db_path)
    store = UsageStore(db_path)

    for day in AUG_DAYS:
        seed_day(store, day, august=True, with_models=False)
    for day in SEP_DAYS:
        seed_day(store, day, august=False, with_models=True)

    # A dormant seat: demo-grace used Copilot back on 2026-08-01, nothing since.
    store.upsert_user_day(
        "2026-08-01",
        SCOPE,
        107,
        user_login="demo-grace",
        ai_credits_used=120.0,
        interactions=200,
        loc_added=900,
    )
    store.close()
    print(f"seeded demo db: {db_path}")


if __name__ == "__main__":
    main()
