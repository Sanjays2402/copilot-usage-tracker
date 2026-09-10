"""In-process data collection shared by the CLI, the GUI, and the tray app.

``run_collection()`` is the same logic as ``copilot-usage collect`` but
callable from anywhere -- the dashboard's "Collect" button and the tray
menu use it directly, so end users never touch a terminal.
"""

from __future__ import annotations

from collections.abc import Callable

from .attribution import attribute_to_teams
from .audit import AuditLogger
from .collector import CopilotReportsClient
from .config import load_settings
from .policy import apply_to_session, load_policy
from .privacy import pseudonym, pseudonym_id
from .store import UsageStore
from .tokens import credits_to_usd

ProgressFn = Callable[[str], None]


def yesterday_str() -> str:
    """Yesterday's date in the user's local timezone, YYYY-MM-DD."""
    from datetime import datetime, timedelta

    return (datetime.now().astimezone().date() - timedelta(days=1)).isoformat()


def wire_client(client, policy):
    apply_to_session(client.session, policy)
    return client


def maybe_anonymize_user(user_id, login, policy):
    if not policy.privacy.anonymize_users:
        return user_id, login
    salt = policy.ensure_salt()
    return pseudonym_id(int(user_id or 0), salt), pseudonym(login or "", salt)


def run_collection(day: str, with_teams: bool = True, progress: ProgressFn | None = None) -> dict:
    """Pull one day's usage reports and store local snapshots.

    Returns a summary dict: day, users, credits, usd, teams, purged.
    Raises TokenNotFoundError / ValueError on auth or config problems.
    """

    def say(msg: str) -> None:
        if progress:
            progress(msg)

    policy = load_policy()
    settings = load_settings(policy)
    scope = settings.enterprise or settings.org
    if not policy.scope_allowed(scope):
        raise ValueError(
            f"Scope {scope!r} is not in policy.yaml allowed_scopes; "
            "collection refused by enterprise policy."
        )
    audit = AuditLogger(policy.audit.path, policy.audit.enabled)
    client = wire_client(CopilotReportsClient(settings, audit=audit), policy)
    store = UsageStore(settings.db_path)
    scope_type = "enterprise" if settings.enterprise else "org"
    collect_per_user = policy.collection.collect_per_user
    drop_raw = policy.privacy.drop_raw_json

    say(f"Downloading usage for {day}…")
    users = client.users_day(day) if collect_per_user else []
    for u in users:
        user_id, login = maybe_anonymize_user(u.get("user_id"), u.get("user_login"), policy)
        store.upsert_user_day(
            day,
            scope,
            user_id,
            user_login=login,
            ai_credits_used=u.get("ai_credits_used", 0) or 0,
            interactions=u.get("user_initiated_interaction_count", 0) or 0,
            loc_added=u.get("loc_added_sum", 0) or 0,
            raw=None if drop_raw else u,
        )

    entity_rows = client.entity_day(day)
    credits = sum(r.get("ai_credits_used", 0) or 0 for r in entity_rows)
    active = sum(1 for u in users if (u.get("ai_credits_used", 0) or 0) > 0)
    store.upsert_scope_day(day, scope, scope_type, ai_credits_used=credits, active_users=active)

    team_count = 0
    if with_teams and collect_per_user:
        say("Attributing usage to teams…")
        teams = attribute_to_teams(users, client.user_teams_day(day))
        for t in teams:
            team_id = t.pop("team_id")
            t.pop("day", None)  # passed positionally below
            store.upsert_team_day(day, scope, team_id, **t)
        team_count = len(teams)

    purged = 0
    if policy.privacy.retention_days > 0:
        counts = store.purge_older_than(policy.privacy.retention_days)
        purged = sum(counts.values())
    store.close()
    say("Done.")
    return {
        "day": day,
        "users": len(users),
        "credits": credits,
        "usd": credits_to_usd(credits),
        "teams": team_count,
        "purged": purged,
    }


def summary_line(summary: dict) -> str:
    return (
        f"Stored {summary['users']} user rows, "
        f"{summary['credits']:,.0f} credits (${summary['usd']:,.2f}), "
        f"{summary['teams']} team rollups for {summary['day']}"
        + (f"; purged {summary['purged']} rows beyond retention" if summary["purged"] else "")
    )
