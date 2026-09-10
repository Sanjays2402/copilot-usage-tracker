"""Seed a demo database with realistic sample data for screenshots.

Run:  COPILOT_DB=docs/screenshots/demo.db python docs/screenshots/seed_demo.py
Then: COPILOT_DB=docs/screenshots/demo.db streamlit run dashboard/app.py

All data is fictional and clearly labeled as a demo.
"""

from __future__ import annotations

import os
import random
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))

from copilot_usage_tracker.store import UsageStore

SCOPE = "acme-corp"
DAYS = [f"2026-09-{d:02d}" for d in range(1, 11)]

USERS = [
    # (user_id, login, team_id, team_slug, base_credits)
    (101, "alice", 1, "platform", 320),
    (102, "bob", 1, "platform", 210),
    (103, "carol", 1, "platform", 150),
    (104, "dave", 2, "mobile", 260),
    (105, "erin", 2, "mobile", 180),
    (106, "frank", 2, "mobile", 90),
]

MODELS = [
    # (model, input_share, output_share, cost_per_1k_usd blended-ish)
    ("gpt-5", 0.55, 0.30, 0.004),
    ("claude-sonnet-4.5", 0.30, 0.45, 0.006),
    ("gpt-5-mini", 0.15, 0.25, 0.001),
]


def main() -> None:
    random.seed(42)
    db_path = os.environ.get("COPILOT_DB", "docs/screenshots/demo.db")
    if os.path.exists(db_path):
        os.remove(db_path)
    store = UsageStore(db_path)

    for day in DAYS:
        weekend = day in ("2026-09-05", "2026-09-06")
        scope_credits = 0.0
        team_credits = {1: 0.0, 2: 0.0}
        team_users = {1: set(), 2: set()}
        for user_id, login, team_id, slug, base in USERS:
            credits = base * random.uniform(0.7, 1.3) * (0.15 if weekend else 1.0)
            credits = round(credits, 1)
            store.upsert_user_day(
                day,
                SCOPE,
                user_id,
                user_login=login,
                ai_credits_used=credits,
                interactions=int(credits * random.uniform(1.5, 2.5)),
                loc_added=int(credits * random.uniform(8, 14)),
            )
            scope_credits += credits
            team_credits[team_id] += credits
            if credits > 1:
                team_users[team_id].add(login)
            # model token rows (per user, per model)
            for model, in_share, out_share, _ in MODELS:
                in_tok = int(credits * 1000 * in_share * random.uniform(0.8, 1.2))
                out_tok = int(credits * 1000 * out_share * random.uniform(0.8, 1.2))
                cache_read = int(in_tok * random.uniform(0.3, 0.6))
                gross = round((in_tok + out_tok * 3) / 1000 * 0.004, 4)
                store.upsert_model_day(
                    day,
                    SCOPE,
                    model,
                    user_login=login,
                    input_tokens=in_tok,
                    output_tokens=out_tok,
                    cache_read_tokens=cache_read,
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
    # A dormant seat: grace used Copilot back in August, nothing since.
    store.upsert_user_day(
        "2026-08-01",
        SCOPE,
        107,
        user_login="grace",
        ai_credits_used=120.0,
        interactions=200,
        loc_added=900,
    )
    store.close()
    print(f"seeded demo db: {db_path}")


if __name__ == "__main__":
    main()
