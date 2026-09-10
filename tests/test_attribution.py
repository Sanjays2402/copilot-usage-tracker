"""Tests for team attribution (user-teams join)."""

from copilot_usage_tracker.attribution import attribute_to_teams

USERS = [
    {
        "user_id": 1001,
        "user_login": "alice",
        "day": "2026-05-07",
        "ai_credits_used": 120.5,
        "user_initiated_interaction_count": 50,
        "code_generation_activity_count": 40,
        "code_acceptance_activity_count": 12,
        "loc_added_sum": 88,
    },
    {
        "user_id": 1002,
        "user_login": "bob",
        "day": "2026-05-07",
        "ai_credits_used": 30.0,
        "user_initiated_interaction_count": 30,
        "code_generation_activity_count": 25,
        "code_acceptance_activity_count": 7,
        "loc_added_sum": 24,
    },
]

TEAMS = [
    {"user_id": 1001, "day": "2026-05-07", "team_id": 42, "slug": "frontend"},
    {"user_id": 1001, "day": "2026-05-07", "team_id": 43, "slug": "backend"},
    {"user_id": 1002, "day": "2026-05-07", "team_id": 42, "slug": "frontend"},
]


def test_team_aggregation():
    rows = {r["slug"]: r for r in attribute_to_teams(USERS, TEAMS)}
    assert set(rows) == {"frontend", "backend"}
    frontend = rows["frontend"]
    assert frontend["active_users"] == 2
    assert frontend["ai_credits_used"] == 150.5
    assert frontend["loc_added_sum"] == 112
    backend = rows["backend"]
    assert backend["active_users"] == 1
    assert backend["ai_credits_used"] == 120.5


def test_multi_team_user_counts_in_each_team():
    rows = {r["slug"]: r for r in attribute_to_teams(USERS, TEAMS)}
    # alice belongs to both teams; her credits appear in each (documented)
    assert rows["frontend"]["ai_credits_used"] + rows["backend"]["ai_credits_used"] == 271.0


def test_user_without_team_row_is_unattributed():
    teams = [t for t in TEAMS if t["user_id"] != 1002]
    rows = {r["slug"]: r for r in attribute_to_teams(USERS, teams)}
    assert rows["frontend"]["active_users"] == 1  # only alice
    assert all(r["slug"] != "unattributed" for r in rows.values())
