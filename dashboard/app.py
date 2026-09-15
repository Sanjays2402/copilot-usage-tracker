"""Streamlit dashboard for copilot-usage-tracker.

Run from the repo root (with the package installed):

    streamlit run dashboard/app.py

Reads the SQLite store populated by `copilot-usage collect` and
`copilot-usage export-tokens`.
"""

from __future__ import annotations

import os
import re
import sys

try:
    import copilot_usage_tracker  # noqa: F401
except ImportError:  # dev fallback: run from repo root without install
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import pandas as pd
import streamlit as st

from copilot_usage_tracker import appconfig
from copilot_usage_tracker.audit import read_audit_log
from copilot_usage_tracker.auth import (
    TokenNotFoundError,
    mask_token,
    resolve_token,
    save_to_keyring,
    validate_token,
)
from copilot_usage_tracker.budgets import Budget, check_budgets
from copilot_usage_tracker.insights import (
    daily_spend_series,
    dormant_seats,
    engagement_daily_series,
    engagement_summary,
    executive_summary,
    forecast_month_end,
    model_breakdown,
    month_over_month,
    monthly_kpis,
    spike_alerts,
    team_leaderboard,
    top_users_with_cost,
)
from copilot_usage_tracker.notify import notify_budget_alerts, send_webhook
from copilot_usage_tracker.policy import load_policy
from copilot_usage_tracker.store import UsageStore
from copilot_usage_tracker.sync import run_collection, summary_line, yesterday_str
from copilot_usage_tracker.tokens import PriceBook
from copilot_usage_tracker.trust import (
    data_inventory,
    network_summary,
    token_privilege_verdict,
)


def _setup_page() -> None:
    """First-run onboarding: scope + token, no terminal required."""
    st.title("Welcome to Copilot Usage Tracker")
    st.write(
        "Connect your GitHub enterprise or organization once. Everything stays on this machine."
    )
    cfg = appconfig.load_app_config()

    scope_kind = st.radio(
        "What do you want to track?",
        ["Organization", "Enterprise"],
        index=0 if not cfg.enterprise else 1,
        horizontal=True,
    )
    slug = st.text_input(
        "Organization login" if scope_kind == "Organization" else "Enterprise slug",
        value=cfg.org if scope_kind == "Organization" else cfg.enterprise,
        placeholder="e.g. acme-corp",
    ).strip()

    _resolved: str | None = None
    try:
        _token, source = resolve_token()
        st.success(f"GitHub token found via {source} ({mask_token(_token)}).")
        _resolved = _token
        token: str | None = None
    except TokenNotFoundError:
        st.write(
            "A GitHub token lets the app download usage reports. "
            "[Create a fine-grained token](https://github.com/settings/tokens) "
            "with read access to Copilot business metrics — it is stored "
            "only in your OS keyring, never in a file."
        )
        token = st.text_input("GitHub token", type="password").strip() or None

    consent = st.checkbox(
        "I understand this app downloads Copilot usage reports from GitHub "
        "and stores them only on this machine. It never sends data anywhere "
        "else.",
        value=False,
    )

    remember = st.checkbox("Remember the token on this machine (OS keyring)", value=True)
    if st.button("Save & connect", type="primary"):
        if not slug:
            st.error("Enter your organization login or enterprise slug.")
            st.stop()
        if not consent:
            st.error("Please confirm you understand how your data is handled.")
            st.stop()
        api_base = cfg.api_base
        check_token = token or _resolved
        if check_token:
            try:
                login, token_scopes = validate_token(check_token, api_base)
            except Exception as exc:  # noqa: BLE001 - show validation errors plainly
                st.error(f"That token didn't work: {exc}")
                st.stop()
            st.success(f"Token works — signed in as @{login}.")
            verdict = token_privilege_verdict(token_scopes)
            if verdict["level"] == "elevated":
                st.warning(verdict["message"])
            elif verdict["level"] == "unknown":
                st.info(verdict["message"])
            else:
                st.success(verdict["message"])
            if remember:
                try:
                    save_to_keyring(token)
                except Exception as exc:  # noqa: BLE001 - keyring may be unavailable
                    st.warning(
                        f"Could not use the OS keyring ({exc}); "
                        "set GITHUB_TOKEN in your environment instead."
                    )
        cfg.enterprise = slug if scope_kind == "Enterprise" else ""
        cfg.org = slug if scope_kind == "Organization" else ""
        appconfig.save_app_config(cfg)
        st.success("Connected. Fetching yesterday's usage…")
        _collect_latest(cfg)
        st.rerun()


def _collect_latest(cfg) -> dict | None:
    day = yesterday_str()
    with st.spinner(f"Collecting usage for {day}…"):
        try:
            summary = run_collection(day, with_teams=cfg.with_teams)
        except (TokenNotFoundError, ValueError) as exc:
            st.error(str(exc))
            return None
    st.success(summary_line(summary))
    return summary


def _maybe_notify(cfg, spent_usd: float) -> None:
    """Push budget alerts to the configured chat webhook, if any."""
    if not cfg.webhook_url:
        return
    budget = Budget(scope="all", limit_usd=cfg.budget_limit_usd, spent_usd=spent_usd)
    alerts = check_budgets([budget])
    if not alerts:
        return
    results = notify_budget_alerts(cfg.webhook_url, alerts)
    sent = sum(1 for r in results if r.ok)
    if sent == len(results):
        st.info(f"📣 Sent {sent} budget alert(s) to the chat webhook.")
    else:
        st.warning(
            f"Webhook delivery failed for {len(results) - sent} alert(s): "
            + "; ".join(r.error for r in results if not r.ok)[:200]
        )


THEMES = {
    "Quiet Ledger": "ledger",
    "OLED Black": "oled",
    "Slate": "slate",
}


def _inject_theme() -> None:
    """Load the dashboard theme: base component CSS + selected palette."""
    try:
        name = appconfig.load_app_config().theme
    except Exception:  # noqa: BLE001 - config optional
        name = "ledger"
    if name not in THEMES.values():
        name = "ledger"
    base_path = os.path.join(os.path.dirname(__file__), "themes", "base.css")
    theme_path = os.path.join(os.path.dirname(__file__), "themes", f"{name}.css")
    css = ""
    for path in (base_path, theme_path):
        try:
            with open(path, encoding="utf-8") as fh:
                css += fh.read() + "\n"
        except OSError:
            pass
    if css:
        st.markdown(f"<style>{css}</style>", unsafe_allow_html=True)


_inject_theme()

if not appconfig.is_configured():
    _setup_page()
    st.stop()

# -- sidebar ---------------------------------------------------------------
st.sidebar.title("Configuration")
db_path = st.sidebar.text_input(
    "Database",
    value=os.environ.get("COPILOT_DB") or appconfig.default_db_path(),
)
scope = st.sidebar.text_input("Scope (blank = all)", value="")
month = st.sidebar.text_input("Month (YYYY-MM)", value="2026-09")
plan = st.sidebar.selectbox("Plan", ["business", "enterprise"])
seats = st.sidebar.number_input("Granted seats", min_value=0, value=0, step=10)
overage = st.sidebar.checkbox("Bill overage beyond pooled allowance", value=False)
scope = scope or None
_cfg = appconfig.load_app_config()

st.sidebar.subheader("Appearance")
_theme_labels = list(THEMES)
_current_theme = _cfg.theme if _cfg.theme in THEMES.values() else "ledger"
_theme_label = st.sidebar.selectbox(
    "Theme",
    _theme_labels,
    index=list(THEMES.values()).index(_current_theme),
    label_visibility="collapsed",
)
if THEMES[_theme_label] != _cfg.theme:
    _cfg.theme = THEMES[_theme_label]
    appconfig.save_app_config(_cfg)
    st.rerun()

st.sidebar.divider()
st.sidebar.subheader("Data")
if st.sidebar.button("🔄 Collect latest", use_container_width=True):
    if _collect_latest(_cfg) is not None:
        st.session_state["just_collected"] = True
    st.rerun()
with st.sidebar.expander("Settings"):
    new_kind = st.radio(
        "Scope type",
        ["Organization", "Enterprise"],
        index=1 if _cfg.enterprise else 0,
        horizontal=True,
    )
    new_slug = st.text_input(
        "Slug",
        value=_cfg.enterprise or _cfg.org,
    ).strip()
    new_teams = st.checkbox("Build per-team rollups", value=_cfg.with_teams)
    new_hours = st.number_input(
        "Auto-collect every N hours (0 = off)",
        min_value=0.0,
        value=float(_cfg.auto_collect_hours),
        step=1.0,
    )
    new_webhook = st.text_input(
        "Chat webhook URL (Slack/Teams) for budget alerts",
        value=_cfg.webhook_url,
        type="password",
    ).strip()
    if st.button("Save settings"):
        if not new_slug:
            st.error("Enter your organization login or enterprise slug.")
        else:
            _cfg.enterprise = new_slug if new_kind == "Enterprise" else ""
            _cfg.org = new_slug if new_kind == "Organization" else ""
            _cfg.with_teams = new_teams
            _cfg.auto_collect_hours = new_hours
            _cfg.webhook_url = new_webhook
            appconfig.save_app_config(_cfg)
            st.success("Saved.")
            st.rerun()
    try:
        _tok, _src = resolve_token()
        st.caption(f"Token: {_src} ({mask_token(_tok)})")
    except TokenNotFoundError:
        st.caption("Token: not found — run `copilot-usage login` or redo setup.")

book = PriceBook.for_plan(plan, overage_allowed=overage)

# -- data ------------------------------------------------------------------
try:
    store = UsageStore(db_path)
except Exception as exc:  # noqa: BLE001 - surface config errors plainly
    st.error(f"Could not open database {db_path}: {exc}")
    st.stop()

kpis = monthly_kpis(store, month, scope, book, seats)
daily = daily_spend_series(store, month, scope)
teams = team_leaderboard(store, month, scope)
users = top_users_with_cost(store, month, scope)
models = model_breakdown(store, month, scope)
forecast = forecast_month_end(store, month, scope, book, seats)
engagement = engagement_summary(store, month, scope)
engagement_daily = engagement_daily_series(store, month, scope)
seats_report = dormant_seats(store, 30, scope, book)
mom = month_over_month(store, month, scope, book, seats)
spikes = spike_alerts(store, month, scope)
summary_md = executive_summary(
    store,
    month,
    scope,
    book,
    seats,
    budget_limit_usd=_cfg.budget_limit_usd,
)


def _delta_credits(v: float) -> str:
    return f"{v:+,.0f} credits"


def _delta_usd(v: float) -> str:
    sign = "+" if v >= 0 else "-"
    return f"{sign}${abs(v):,.2f}"


def _delta_users(v: int) -> str:
    noun = "user" if abs(v) == 1 else "users"
    return f"{v:+,} {noun}"


def _delta_utilization(v: float) -> str:
    return f"{v:+.1f}pp"


# ---------------------------------------------------------------------------
# Presentation components ("Quiet Ledger" design system)
# ---------------------------------------------------------------------------

def _kpi(
    label: str,
    value: str,
    delta: str | None = None,
    bad_when_up: bool = False,
    small: bool = False,
) -> str:
    """Render a KPI card. `delta` is a preformatted string like "+$12.34"."""
    pill = ""
    if delta:
        m = re.search(r"[\d.]+", delta)
        num = float(m.group()) if m else 0.0
        s = delta.strip()
        up = s.startswith("+") and num != 0
        down = s.startswith("-") and num != 0
        if num == 0:
            tone = "neutral"
        elif bad_when_up:
            tone = "bad" if up else "good"
        else:
            tone = "good" if up else "bad"
        arrow = "\u2191" if up else ("\u2193" if down else "\u2192")
        pill = (
            f'<span class="cut-delta cut-delta-{tone}">'
            f'<span class="cut-delta-arrow">{arrow}</span>{delta}</span>'
        )
    cls = "cut-kpi cut-kpi-small" if small else "cut-kpi"
    return (
        f'<div class="{cls}">'
        f'<div class="cut-kpi-label">{label}</div>'
        f'<div class="cut-kpi-value">{value}</div>'
        f"{pill}"
        "</div>"
    )


def _section(title: str, hint: str | None = None) -> str:
    """Render a section header, optionally with a muted hint line."""
    hint_html = f'<div class="cut-section-hint">{hint}</div>' if hint else ""
    return (
        '<div class="cut-section">'
        f'<div class="cut-section-title">{title}</div>'
        f"{hint_html}"
        "</div>"
    )


def _page_header() -> str:
    """Render the dashboard page header (replaces st.title + st.caption)."""
    return (
        '<div class="cut-pagehead">'
        '<div class="cut-eyebrow">GitHub Copilot</div>'
        '<h1 class="cut-title">Usage &amp; cost</h1>'
        f'<div class="cut-meta">Scope: {scope} &middot; {month} &middot; '
        f"{plan} plan &middot; {seats} seats</div>"
        "</div>"
    )


if st.session_state.pop("just_collected", False):
    _maybe_notify(_cfg, kpis["total_cost_usd"])

st.markdown(_page_header(), unsafe_allow_html=True)

policy_path = os.environ.get("COPILOT_POLICY_FILE", "policy.yaml")
if os.path.exists(policy_path):
    st.sidebar.caption("🔒 Enterprise policy active (policy.yaml)")
st.sidebar.caption(
    "All data stays on this machine — the only network calls are to your "
    "GitHub API endpoint. No third-party telemetry."
)

(
    tab_overview,
    tab_engage,
    tab_teams,
    tab_users,
    tab_seats,
    tab_models,
    tab_budgets,
    tab_audit,
    tab_security,
) = st.tabs(
    [
        "Overview",
        "Engagement",
        "Teams",
        "Users",
        "Seats",
        "Models & Tokens",
        "Budgets",
        "Audit",
        "Security",
    ]
)

# Audit records feed both the Audit tab and the Security tab's network proof.
audit_path = os.environ.get("COPILOT_AUDIT_FILE")
if not audit_path:
    try:
        audit_path = load_policy().audit.path
    except Exception:  # noqa: BLE001 - policy optional
        audit_path = os.path.expanduser("~/.copilot-usage-tracker/audit.jsonl")
audit_records = read_audit_log(audit_path, limit=500)
api_base = _cfg.api_base

with tab_overview:
    c1, c2, c3, c4 = st.columns(4)
    c1.markdown(_kpi("Total cost", f"${kpis['total_cost_usd']:,.2f}", delta=_delta_usd(mom["total_cost"]["delta"]), bad_when_up=True), unsafe_allow_html=True)
    c2.markdown(_kpi("Credits used", f"{kpis['credits_used']:,.0f}", delta=_delta_credits(mom["credits"]["delta"]), bad_when_up=True), unsafe_allow_html=True)
    c3.markdown(_kpi("Active users", f"{kpis['active_users']:,}", delta=_delta_users(mom["active_users"]["delta"]), bad_when_up=False), unsafe_allow_html=True)
    allowance = book.pooled_allowance(seats)
    util_delta = mom["credits"]["delta"] / allowance * 100 if allowance else 0.0
    c4.markdown(_kpi("Allowance utilization", f"{kpis['utilization']:.1%}", delta=_delta_utilization(util_delta), bad_when_up=True), unsafe_allow_html=True)
    st.download_button(
        "📝 Download summary (Markdown)",
        summary_md.encode("utf-8"),
        file_name=f"copilot-summary-{month}.md",
        mime="text/markdown",
    )
    c1, c2, c3 = st.columns(3)
    c1.markdown(_kpi("Seat cost", f"${kpis['seat_cost_usd']:,.2f}"), unsafe_allow_html=True)
    c2.markdown(_kpi("Overage cost", f"${kpis['overage_cost_usd']:,.2f}"), unsafe_allow_html=True)
    c3.markdown(_kpi("Input / Output tokens", f"{kpis['input_tokens']:,} / {kpis['output_tokens']:,}"), unsafe_allow_html=True)
    if spikes:
        st.markdown(_section("Unusual activity"), unsafe_allow_html=True)
        st.write(
            "Users whose latest day's credits are at least 3× their "
            "trailing daily average — worth a quick look for runaway "
            "agents or shared accounts."
        )
        df = pd.DataFrame(
            [
                {
                    "User": a["user"],
                    "Latest day": a["latest_day"],
                    "Credits vs avg": (f"{a['latest_credits']:,.0f} vs {a['trailing_avg']:,.0f}"),
                    "Multiple": f"{a['multiple']:.1f}×",
                }
                for a in spikes
            ]
        )
        st.dataframe(df, use_container_width=True)
    st.markdown(_section("Month-end forecast"), unsafe_allow_html=True)
    f1, f2, f3, f4 = st.columns(4)
    f1.markdown(_kpi("Projected cost", f"${forecast['projected_total_usd']:,.2f}"), unsafe_allow_html=True)
    f2.markdown(_kpi("Projected credits", f"{forecast['projected_credits']:,.0f}"), unsafe_allow_html=True)
    f3.markdown(_kpi("Daily run rate", f"{forecast['daily_run_rate']:,.0f} cr/day"), unsafe_allow_html=True)
    f4.markdown(_kpi("Data coverage", f"{forecast['days_elapsed']}/{forecast['days_in_month']} days"), unsafe_allow_html=True)
    if daily:
        df = pd.DataFrame(daily)
        st.markdown(_section("Daily credit burn"), unsafe_allow_html=True)
        st.bar_chart(df.set_index("day")["credits"])
        st.markdown(_section("Daily spend ($)"), unsafe_allow_html=True)
        st.line_chart(df.set_index("day")["usd"])
    else:
        st.info(f"No daily data for {month}. Hit “🔄 Collect latest” above — no terminal needed.")

with tab_engage:
    e1, e2, e3, e4 = st.columns(4)
    e1.markdown(_kpi("Copilot interactions", f"{engagement['interactions']:,}"), unsafe_allow_html=True)
    e2.markdown(_kpi("Lines of code added", f"{engagement['loc_added']:,}"), unsafe_allow_html=True)
    e3.markdown(_kpi("Engaged users", f"{engagement['engaged_users']:,} / {engagement['active_users']:,}"), unsafe_allow_html=True)
    e4.markdown(_kpi("Engagement rate", f"{engagement['engagement_rate']:.1%}"), unsafe_allow_html=True)
    e1, e2 = st.columns(2)
    e1.markdown(_kpi("Interactions / engaged user", f"{engagement['interactions_per_engaged_user']:,}"), unsafe_allow_html=True)
    e2.markdown(_kpi("Lines added / engaged user", f"{engagement['loc_per_engaged_user']:,}"), unsafe_allow_html=True)
    if engagement_daily:
        df = pd.DataFrame(engagement_daily)
        st.markdown(_section("Daily interactions"), unsafe_allow_html=True)
        st.bar_chart(df.set_index("day")["interactions"])
        st.markdown(_section("Daily engaged users"), unsafe_allow_html=True)
        st.line_chart(df.set_index("day")["engaged_users"])
    else:
        st.info(f"No engagement data for {month} yet.")

with tab_teams:
    if teams:
        df = pd.DataFrame(teams)
        st.bar_chart(df.set_index("team")["credits"])
        st.dataframe(df, use_container_width=True)
        st.download_button(
            "⬇ Download teams CSV",
            df.to_csv(index=False).encode("utf-8"),
            file_name=f"copilot-teams-{month}.csv",
            mime="text/csv",
        )
    else:
        st.info("No team data. Hit “🔄 Collect latest” with per-team rollups enabled.")

with tab_users:
    if users:
        df = pd.DataFrame(users)
        st.dataframe(df, use_container_width=True)
        st.markdown(_section("User drill-down"), unsafe_allow_html=True)
        logins = [u["user"] for u in users]
        picked = st.selectbox("User", logins, index=0, help="Defaults to the top credit consumer.")
        series = store.user_daily_series(picked, month, scope)
        sdf = pd.DataFrame(series).set_index("day")
        u1, u2 = st.columns(2)
        u1.markdown(_kpi("Total credits", f"{sdf['credits'].sum():,.0f}"), unsafe_allow_html=True)
        u2.markdown(_kpi("Total interactions", f"{sdf['interactions'].sum():,}"), unsafe_allow_html=True)
        st.bar_chart(sdf["credits"])
        st.caption("Daily credits")
        st.line_chart(sdf["interactions"])
        st.caption("Daily interactions")
        st.download_button(
            "⬇ Download users CSV",
            df.to_csv(index=False).encode("utf-8"),
            file_name=f"copilot-users-{month}.csv",
            mime="text/csv",
        )
    else:
        st.info("No user data for this month yet.")

with tab_seats:
    st.markdown(_section("Seat reclamation"), unsafe_allow_html=True)
    st.write(
        "Seats with no Copilot usage in the trailing 30 days are candidates "
        "for license reclamation."
    )
    s1, s2 = st.columns(2)
    s1.markdown(_kpi("Dormant seats", f"{seats_report['dormant_count']:,}"), unsafe_allow_html=True)
    s2.markdown(_kpi("Potential monthly savings", f"${seats_report['potential_monthly_savings_usd']:,.2f}"), unsafe_allow_html=True)
    if seats_report["users"]:
        df = pd.DataFrame(seats_report["users"])
        st.dataframe(df, use_container_width=True)
        st.download_button(
            "⬇ Download dormant seats CSV",
            df.to_csv(index=False).encode("utf-8"),
            file_name=f"copilot-dormant-seats-{month}.csv",
            mime="text/csv",
        )
    else:
        st.success("No dormant seats — everyone used Copilot in the last 30 days.")

with tab_models:
    if models:
        df = pd.DataFrame(models)
        st.markdown(_section("Input vs output tokens by model"), unsafe_allow_html=True)
        st.bar_chart(df.set_index("model")[["input_tokens", "output_tokens"]])
        st.markdown(_section("Cost by model"), unsafe_allow_html=True)
        st.dataframe(
            df[
                [
                    "model",
                    "input_tokens",
                    "output_tokens",
                    "cache_read_tokens",
                    "gross_usd",
                    "net_usd",
                ]
            ],
            use_container_width=True,
        )
        st.download_button(
            "⬇ Download models CSV",
            df.to_csv(index=False).encode("utf-8"),
            file_name=f"copilot-models-{month}.csv",
            mime="text/csv",
        )
    else:
        st.info(
            "No per-model token data. Hit “🔄 Collect latest”, then use the "
            "CLI `copilot-usage export-tokens --year 2026 --month 9` to pull "
            "the AI usage report (input/output/cache tokens per model)."
        )

with tab_budgets:
    limit = st.number_input(
        "Monthly budget (USD)",
        min_value=0.0,
        value=float(_cfg.budget_limit_usd),
        step=50.0,
    )
    if limit != _cfg.budget_limit_usd:
        _cfg.budget_limit_usd = limit
        appconfig.save_app_config(_cfg)
    budget = Budget(scope=scope or "all", limit_usd=limit, spent_usd=kpis["total_cost_usd"])
    st.progress(
        min(budget.utilization, 1.0), text=f"${budget.spent_usd:,.2f} of ${budget.limit_usd:,.2f}"
    )
    alerts = check_budgets([budget])
    if alerts:
        for a in alerts:
            (st.error if a.status == "breached" else st.warning)(a.message)
    else:
        st.success("Within budget.")
    st.divider()
    st.markdown(_section("Chat alerts"), unsafe_allow_html=True)
    if _cfg.webhook_url:
        st.caption("Webhook configured — alerts are sent automatically after each collection.")
        if st.button("Send test alert"):
            res = send_webhook(
                _cfg.webhook_url,
                "👋 Test alert from Copilot Usage Tracker — webhooks are working.",
            )
            if res.ok:
                st.success("Test message delivered.")
            else:
                st.error(f"Delivery failed: {res.error or res.status}")
        if alerts and st.button("Notify channel now"):
            results = notify_budget_alerts(_cfg.webhook_url, alerts)
            if all(r.ok for r in results):
                st.success(f"Sent {len(results)} alert(s).")
            else:
                st.error("Some deliveries failed — check the webhook URL in Settings.")
    else:
        st.info(
            "Add a Slack/Teams incoming-webhook URL in Settings (sidebar) "
            "to get budget alerts in chat."
        )

with tab_audit:
    st.markdown(_section("API audit log"), unsafe_allow_html=True)
    st.write(
        "Every GitHub API call the app makes is logged here (auth headers "
        "are never recorded). Compliance teams can verify the tool is "
        "read-only."
    )
    records = audit_records
    if records:
        df = pd.DataFrame(
            [
                {
                    "time": r.get("ts", ""),
                    "method": r.get("method", ""),
                    "host": r.get("host", ""),
                    "path": r.get("path", ""),
                    "status": r.get("status", ""),
                }
                for r in records
            ]
        )
        st.dataframe(df, use_container_width=True)
        st.caption(f"Showing {len(records)} most recent entries from {audit_path}")
    else:
        st.info("No audit entries yet — they appear after the first collection.")

with tab_security:
    st.markdown(_section("🔒 Security & privacy"), unsafe_allow_html=True)
    st.write(
        "Everything this app does with your token and your data, "
        "verifiable right here. See [SECURITY.md](https://github.com/"
        "Sanjays2402/copilot-usage-tracker/blob/main/SECURITY.md) for the "
        "full threat model."
    )

    st.markdown("**Your GitHub token**")
    try:
        _tok, _src = resolve_token()
        c1, c2 = st.columns(2)
        c1.markdown(_kpi("Token source", _src, small=True), unsafe_allow_html=True)
        c2.markdown(_kpi("Token value", mask_token(_tok), small=True), unsafe_allow_html=True)
        if st.button("Check token privileges"):
            with st.spinner("Asking GitHub about this token's scopes…"):
                try:
                    _login, _scopes = validate_token(_tok, api_base)
                    verdict = token_privilege_verdict(_scopes)
                    if verdict["level"] == "elevated":
                        st.warning(verdict["message"])
                    elif verdict["level"] == "unknown":
                        st.info(verdict["message"])
                    else:
                        st.success(verdict["message"])
                except Exception as exc:  # noqa: BLE001 - network may fail
                    st.error(f"Could not check scopes: {exc}")
        st.caption(
            "The app never stores your token — not in files, not in the "
            "database, not in logs. It lives in your OS keyring or "
            "environment and only in process memory."
        )
    except TokenNotFoundError:
        st.warning("No token found.")

    st.markdown("**Network proof — the app is read-only**")
    net = network_summary(audit_records, api_base)
    n1, n2, n3 = st.columns(3)
    n1.markdown(_kpi("API requests logged", f"{net['total_requests']:,}"), unsafe_allow_html=True)
    n2.markdown(_kpi("Non-GET requests", f"{net['non_get_requests']:,}"), unsafe_allow_html=True)
    n3.markdown(_kpi("Third-party hosts contacted", f"{len(net['third_party_hosts']):,}"), unsafe_allow_html=True)
    if net["read_only"] and net["local_only"] and net["total_requests"]:
        st.success(
            "Verified from the audit log: every request was a read-only "
            "GET to your GitHub API host. Nothing was ever sent anywhere else."
        )
    elif not net["total_requests"]:
        st.info("No API calls logged yet — collect data first.")
    else:
        st.warning(
            "Unexpected traffic detected — review the Audit tab. "
            f"Methods: {net['methods']}, other hosts: {net['third_party_hosts']}"
        )

    st.markdown("**What is stored on this machine**")
    inv = data_inventory(store)
    st.dataframe(pd.DataFrame(inv), use_container_width=True)
    st.caption(f"Database file: {db_path}")
    if st.button("🗑 Delete all local data", type="secondary"):
        st.session_state["confirm_wipe"] = True
    if st.session_state.get("confirm_wipe"):
        st.warning(
            "This permanently deletes the local database (all collected "
            "usage data). Your GitHub token in the OS keyring is untouched."
        )
        c1, c2 = st.columns(2)
        if c1.button("Yes, delete everything", type="primary"):
            store.close()
            try:
                os.remove(db_path)
                st.session_state.pop("confirm_wipe", None)
                st.success("Local data deleted.")
                st.rerun()
            except OSError as exc:
                st.error(f"Could not delete: {exc}")
        if c2.button("Cancel"):
            st.session_state.pop("confirm_wipe", None)
            st.rerun()

store.close()
