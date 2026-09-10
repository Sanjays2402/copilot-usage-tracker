"""Team-level attribution via the documented user-teams join.

GitHub publishes no pre-aggregated team report. Team metrics are built by
joining the daily per-user usage report with the same day's user-teams
report on ``(user_id, day)`` and aggregating by team.

Caveats (from GitHub's docs):
- Teams with fewer than 5 seated Copilot users are excluded from the
  user-teams report; their activity still exists in the per-user report but
  cannot be attributed to a team.
- A user on multiple teams contributes to *each* team. Do not sum team
  rows back into an org/enterprise total -- use the per-user report
  directly for entity totals.
- Always join daily reports with daily user-teams (never a 28-day activity
  report against a single-day membership snapshot).
"""

from __future__ import annotations


def attribute_to_teams(
    user_rows: list[dict], team_rows: list[dict]
) -> list[dict]:
    """Aggregate per-user usage rows into per-team rows.

    Returns one dict per (team_id, day) with summed counters and a
    distinct active-user count.
    """
    memberships: dict[tuple, list[dict]] = {}
    for t in team_rows:
        key = (t.get("user_id"), t.get("day"))
        memberships.setdefault(key, []).append(t)

    teams: dict[tuple, dict] = {}
    for u in user_rows:
        day = u.get("day")
        for t in memberships.get((u.get("user_id"), day), []):
            key = (t.get("team_id"), day)
            agg = teams.setdefault(
                key,
                {
                    "team_id": t.get("team_id"),
                    "slug": t.get("slug"),
                    "day": day,
                    "user_ids": set(),
                    "ai_credits_used": 0.0,
                    "user_initiated_interaction_count": 0,
                    "code_generation_activity_count": 0,
                    "code_acceptance_activity_count": 0,
                    "loc_added_sum": 0,
                },
            )
            agg["user_ids"].add(u.get("user_id"))
            for field in (
                "ai_credits_used",
                "user_initiated_interaction_count",
                "code_generation_activity_count",
                "code_acceptance_activity_count",
                "loc_added_sum",
            ):
                agg[field] += u.get(field) or 0

    result = []
    for agg in teams.values():
        agg["active_users"] = len(agg.pop("user_ids"))
        agg["ai_credits_used"] = round(agg["ai_credits_used"], 2)
        result.append(agg)
    result.sort(key=lambda r: (r["day"] or "", r["slug"] or ""))
    return result
