"""Command-line interface."""

from __future__ import annotations

import json

import click

from .attribution import attribute_to_teams
from .audit import AuditLogger
from .billing_reports import BillingReportsClient
from .budgets import Budget, check_budgets
from .collector import BillingClient, CopilotReportsClient
from .config import load_settings
from .policy import (
    PRESET_DESCRIPTIONS,
    apply_to_session,
    default_policy_path,
    load_policy,
    write_preset,
)
from .privacy import pseudonym, pseudonym_id
from .store import UsageStore
from .tokens import PriceBook, credits_to_usd


def _policy_and_settings():
    """Load policy.yaml (if present), then settings honoring it."""
    policy = load_policy()
    settings = load_settings(policy)
    scope = settings.enterprise or settings.org
    if not policy.scope_allowed(scope):
        raise click.ClickException(
            f"Scope {scope!r} is not in policy.yaml allowed_scopes; "
            "collection refused by enterprise policy."
        )
    audit = AuditLogger(policy.audit.path, policy.audit.enabled)
    return policy, settings, scope, audit


def _wire_client(client, policy):
    apply_to_session(client.session, policy)
    return client


def _maybe_anonymize_user(user_id, login, policy):
    if not policy.privacy.anonymize_users:
        return user_id, login
    salt = policy.ensure_salt()
    return pseudonym_id(int(user_id or 0), salt), pseudonym(login or "", salt)


@click.group()
@click.version_option()
def main() -> None:
    """Track GitHub Copilot AI-credit usage and dollar costs at enterprise scale."""


@main.command("init-policy")
@click.option(
    "--preset",
    type=click.Choice(sorted(PRESET_DESCRIPTIONS)),
    default="standard",
    help="; ".join(f"{k}: {v}" for k, v in PRESET_DESCRIPTIONS.items()),
)
@click.option("--output", default=str(default_policy_path()),
              help="Where to write policy.yaml")
def init_policy(preset: str, output: str) -> None:
    """Write a starter enterprise policy file (adapts the tool to company rules)."""
    path = write_preset(preset, output)
    click.echo(f"Wrote {path} (preset: {preset})")
    click.echo("Review it, set allowed_scopes if needed, then re-run your commands.")


@main.command()
@click.option("--days", type=int, default=None,
              help="Purge rows older than N days (default: policy retention_days)")
def purge(days: int | None) -> None:
    """Delete stored rows older than the retention window."""
    policy = load_policy()
    days = days if days is not None else policy.privacy.retention_days
    if not days or days <= 0:
        raise click.ClickException(
            "No retention window configured: pass --days or set "
            "privacy.retention_days in policy.yaml"
        )
    settings = load_settings(policy)
    store = UsageStore(settings.db_path)
    counts = store.purge_older_than(days)
    store.close()
    total = sum(counts.values())
    click.echo(f"Purged {total} rows older than {days} days: {counts}")


@main.command()
@click.option("--day", required=True, help="Report day as YYYY-MM-DD")
@click.option("--with-teams", is_flag=True, help="Also fetch user-teams and build team rollups")
def collect(day: str, with_teams: bool) -> None:
    """Pull a day's usage reports from GitHub and store local snapshots."""
    policy, settings, scope, audit = _policy_and_settings()
    client = _wire_client(CopilotReportsClient(settings, audit=audit), policy)
    store = UsageStore(settings.db_path)
    scope_type = "enterprise" if settings.enterprise else "org"
    collect_per_user = policy.collection.collect_per_user
    drop_raw = policy.privacy.drop_raw_json

    users = client.users_day(day) if collect_per_user else []
    for u in users:
        user_id, login = _maybe_anonymize_user(
            u.get("user_id"), u.get("user_login"), policy
        )
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
    store.upsert_scope_day(
        day, scope, scope_type, ai_credits_used=credits, active_users=active
    )

    team_count = 0
    if with_teams and collect_per_user:
        teams = attribute_to_teams(users, client.user_teams_day(day))
        for t in teams:
            store.upsert_team_day(day, scope, t["team_id"], **t)
        team_count = len(teams)

    purged = ""
    if policy.privacy.retention_days > 0:
        counts = store.purge_older_than(policy.privacy.retention_days)
        purged = f"; purged {sum(counts.values())} rows beyond retention"

    click.echo(
        f"Stored {len(users)} user rows, {credits:,.0f} credits "
        f"(${credits_to_usd(credits):,.2f}), {team_count} team rollups for {day}"
        f"{purged}"
    )
    store.close()


@main.command("export-tokens")
@click.option("--year", type=int, required=True)
@click.option("--month", type=int, required=True)
@click.option(
    "--report-type",
    type=click.Choice(["ai_usage", "summarized", "detailed"]),
    default="ai_usage",
    help="Billing report type to request",
)
def export_tokens(year: int, month: int, report_type: str) -> None:
    """Pull the AI usage report export (per-model input/output tokens + $).

    Uses the billing reports export API -- the only server-side source of
    per-user/day/model token counts. Verify the request payload against
    GitHub's current billing-reports docs if the API rejects it.
    """
    policy, settings, scope, audit = _policy_and_settings()
    client = _wire_client(BillingReportsClient(settings, audit=audit), policy)
    store = UsageStore(settings.db_path)

    payload = {"type": report_type, "year": year, "month": month}
    click.echo(f"Requesting {report_type} report for {year}-{month:02d} ...")
    report_id = client.create_report(payload)
    url = client.wait_for_report(report_id)
    rows = client.download_csv(url)
    click.echo(f"Downloaded {len(rows)} rows")

    anonymize = policy.privacy.anonymize_users
    salt = policy.ensure_salt() if anonymize else ""
    stored = 0
    for r in rows:
        user = str(r.get("user") or r.get("user_login") or "")
        if anonymize and user:
            user = pseudonym(user, salt)
        store.upsert_model_day(
            str(r.get("day") or r.get("date") or f"{year}-{month:02d}-01"),
            scope,
            str(r.get("model") or r.get("sku") or "unknown"),
            user_login=user,
            input_tokens=r.get("input", 0),
            output_tokens=r.get("output", 0),
            cache_read_tokens=r.get("cache_read", 0),
            cache_write_tokens=r.get("cache_write", 0),
            gross_amount_usd=r.get("gross_amount", 0),
            net_amount_usd=r.get("net_amount", 0),
        )
        stored += 1
    totals = store.model_token_totals(f"{year}-{month:02d}", scope)
    click.echo(
        f"Stored {stored} model rows: "
        f"{totals['input_tokens']:,} input / {totals['output_tokens']:,} output tokens"
    )
    store.close()


@main.command()
@click.option("--month", required=True, help="Billing month as YYYY-MM")
@click.option("--scope", default=None, help="Limit to one scope")
@click.option("--plan", type=click.Choice(["business", "enterprise"]), default="business")
@click.option("--seats", type=int, default=0, help="Granted seats for cost math")
@click.option("--overage/--no-overage", default=False, help="Bill credits beyond the pooled allowance")
def report(month: str, scope: str | None, plan: str, seats: int, overage: bool) -> None:
    """Print the dollar-cost report for a month."""
    policy = load_policy()
    settings = load_settings(policy)
    store = UsageStore(settings.db_path)
    credits = store.monthly_credits(month, scope)
    book = PriceBook.for_plan(plan, overage_allowed=overage)
    result = book.monthly_cost(seats, credits)
    result["month"] = month
    result["scope"] = scope
    result["top_users"] = store.top_users(month)
    click.echo(json.dumps(result, indent=2))
    store.close()


@main.command()
@click.option("--year", type=int, required=True)
@click.option("--month", type=int, required=True)
@click.option("--user", default=None, help="Single user login (enterprise billing API)")
def billing(year: int, month: int, user: str | None) -> None:
    """Dump exact AI-credit billing items from GitHub's billing API."""
    policy, settings, _scope, audit = _policy_and_settings()
    client = _wire_client(BillingClient(settings, audit=audit), policy)
    items = client.ai_credit_usage(year, month, user=user)
    click.echo(json.dumps(items, indent=2)[:4000])


@main.command()
@click.option("--limit", type=float, required=True, help="Budget limit in USD")
@click.option("--spent", type=float, required=True, help="Spend so far in USD")
@click.option("--scope", default="enterprise")
def budget_check(limit: float, spent: float, scope: str) -> None:
    """Evaluate a budget and print any alerts."""
    alerts = check_budgets([Budget(scope=scope, limit_usd=limit, spent_usd=spent)])
    if not alerts:
        click.echo("OK: within budget")
    for a in alerts:
        click.echo(a.message)


@main.command()
@click.option("--credits", type=float, required=True, help="AI credits consumed")
@click.option("--seats", type=int, default=0)
@click.option("--plan", type=click.Choice(["business", "enterprise"]), default="business")
@click.option("--overage/--no-overage", default=False)
def estimate(credits: float, seats: int, plan: str, overage: bool) -> None:
    """Estimate a month's dollar cost from credit usage and a price book."""
    book = PriceBook.for_plan(plan, overage_allowed=overage)
    click.echo(json.dumps(book.monthly_cost(seats, credits), indent=2))


@main.command()
def tray() -> None:
    """Launch the desktop system-tray app (popup dashboard on click)."""
    try:
        from tray.app import main as tray_main
    except ImportError as exc:
        raise click.ClickException(
            f"Desktop dependencies missing ({exc}). "
            'Install them with: pip install -e ".[desktop]"'
        ) from exc
    tray_main()


if __name__ == "__main__":
    main()
