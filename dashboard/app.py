"""Streamlit dashboard for copilot-usage-tracker.

Run from the repo root (with the package installed):

    streamlit run dashboard/app.py

Reads the SQLite store populated by `copilot-usage collect` and
`copilot-usage export-tokens`.
"""

from __future__ import annotations

import os
import sys

try:
    import copilot_usage_tracker  # noqa: F401
except ImportError:  # dev fallback: run from repo root without install
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import pandas as pd
import streamlit as st

from copilot_usage_tracker import appconfig
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
    model_breakdown,
    monthly_kpis,
    team_leaderboard,
    top_users_with_cost,
)
from copilot_usage_tracker.store import UsageStore
from copilot_usage_tracker.sync import run_collection, summary_line, yesterday_str
from copilot_usage_tracker.tokens import PriceBook


def _setup_page() -> None:
    """First-run onboarding: scope + token, no terminal required."""
    st.title("Welcome to Copilot Usage Tracker")
    st.write(
        "Connect your GitHub enterprise or organization once. "
        "Everything stays on this machine."
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

    try:
        _token, source = resolve_token()
        st.success(f"GitHub token found via {source} ({mask_token(_token)}).")
        token: str | None = None
    except TokenNotFoundError:
        st.write(
            "A GitHub token lets the app download usage reports. "
            "[Create a fine-grained token](https://github.com/settings/tokens) "
            "with read access to Copilot business metrics — it is stored "
            "only in your OS keyring, never in a file."
        )
        token = st.text_input("GitHub token", type="password").strip() or None

    remember = st.checkbox(
        "Remember the token on this machine (OS keyring)", value=True
    )
    if st.button("Save & connect", type="primary"):
        if not slug:
            st.error("Enter your organization login or enterprise slug.")
            st.stop()
        api_base = cfg.api_base
        if token:
            try:
                login, _scopes = validate_token(token, api_base)
            except Exception as exc:  # noqa: BLE001 - show validation errors plainly
                st.error(f"That token didn't work: {exc}")
                st.stop()
            st.success(f"Token works — signed in as @{login}.")
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


def _collect_latest(cfg) -> None:
    day = yesterday_str()
    with st.spinner(f"Collecting usage for {day}…"):
        try:
            summary = run_collection(day, with_teams=cfg.with_teams)
        except (TokenNotFoundError, ValueError) as exc:
            st.error(str(exc))
            return
    st.success(summary_line(summary))


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

st.sidebar.divider()
st.sidebar.subheader("Data")
_cfg = appconfig.load_app_config()
if st.sidebar.button("🔄 Collect latest", use_container_width=True):
    _collect_latest(_cfg)
    st.rerun()
with st.sidebar.expander("Settings"):
    new_kind = st.radio(
        "Scope type", ["Organization", "Enterprise"],
        index=1 if _cfg.enterprise else 0, horizontal=True,
    )
    new_slug = st.text_input(
        "Slug", value=_cfg.enterprise or _cfg.org,
    ).strip()
    new_teams = st.checkbox("Build per-team rollups", value=_cfg.with_teams)
    if st.button("Save settings"):
        if not new_slug:
            st.error("Enter your organization login or enterprise slug.")
        else:
            _cfg.enterprise = new_slug if new_kind == "Enterprise" else ""
            _cfg.org = new_slug if new_kind == "Organization" else ""
            _cfg.with_teams = new_teams
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

st.title("GitHub Copilot — Usage & Cost")
st.caption(f"Scope: {scope or 'all'} · {month} · {plan} plan · {seats} seats")

policy_path = os.environ.get("COPILOT_POLICY_FILE", "policy.yaml")
if os.path.exists(policy_path):
    st.sidebar.caption("🔒 Enterprise policy active (policy.yaml)")
st.sidebar.caption(
    "All data stays on this machine — the only network calls are to your "
    "GitHub API endpoint. No third-party telemetry."
)

tab_overview, tab_teams, tab_users, tab_models, tab_budgets = st.tabs(
    ["Overview", "Teams", "Users", "Models & Tokens", "Budgets"]
)

with tab_overview:
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Total cost", f"${kpis['total_cost_usd']:,.2f}")
    c2.metric("Credits used", f"{kpis['credits_used']:,.0f}")
    c3.metric("Active users", f"{kpis['active_users']:,}")
    c4.metric("Allowance utilization", f"{kpis['utilization']:.1%}")
    c1, c2, c3 = st.columns(3)
    c1.metric("Seat cost", f"${kpis['seat_cost_usd']:,.2f}")
    c2.metric("Overage cost", f"${kpis['overage_cost_usd']:,.2f}")
    c3.metric("Input / Output tokens",
              f"{kpis['input_tokens']:,} / {kpis['output_tokens']:,}")
    if daily:
        df = pd.DataFrame(daily)
        st.subheader("Daily credit burn")
        st.bar_chart(df.set_index("day")["credits"])
        st.subheader("Daily spend ($)")
        st.line_chart(df.set_index("day")["usd"])
    else:
        st.info(f"No daily data for {month}. Run `copilot-usage collect --day ...` first.")

with tab_teams:
    if teams:
        df = pd.DataFrame(teams)
        st.bar_chart(df.set_index("team")["credits"])
        st.dataframe(df, use_container_width=True)
    else:
        st.info("No team data. Run `copilot-usage collect --day ... --with-teams`.")

with tab_users:
    if users:
        st.dataframe(pd.DataFrame(users), use_container_width=True)
    else:
        st.info("No user data for this month yet.")

with tab_models:
    if models:
        df = pd.DataFrame(models)
        st.subheader("Input vs output tokens by model")
        st.bar_chart(df.set_index("model")[["input_tokens", "output_tokens"]])
        st.subheader("Cost by model")
        st.dataframe(
            df[["model", "input_tokens", "output_tokens",
                "cache_read_tokens", "gross_usd", "net_usd"]],
            use_container_width=True,
        )
    else:
        st.info(
            "No per-model token data. Run "
            "`copilot-usage export-tokens --year 2026 --month 9` to pull the "
            "AI usage report (input/output/cache tokens per model)."
        )

with tab_budgets:
    limit = st.number_input("Monthly budget (USD)", min_value=0.0, value=1000.0, step=50.0)
    budget = Budget(scope=scope or "enterprise", limit_usd=limit,
                    spent_usd=kpis["total_cost_usd"])
    st.progress(min(budget.utilization, 1.0),
                text=f"${budget.spent_usd:,.2f} of ${budget.limit_usd:,.2f}")
    alerts = check_budgets([budget])
    if alerts:
        for a in alerts:
            (st.error if a.status == "breached" else st.warning)(a.message)
    else:
        st.success("Within budget.")

store.close()
