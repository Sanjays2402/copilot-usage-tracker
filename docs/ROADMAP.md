# Roadmap

## v0.1 -- Foundation (this release)
- [x] Report-based collector for the current Copilot usage metrics API
      (`users-1-day`, `entity-1-day`, `user-teams-1-day`, `repos-1-day`;
      NDJSON download flow)
- [x] AI-credit billing client (exact per-user/per-model figures from
      GitHub's billing API)
- [x] SQLite time-series store (per-user, per-scope, per-team daily rows)
- [x] AI-credit cost model (`PriceBook`: 1 credit = $0.01, pooled seat
      allowances, overage math)
- [x] Team attribution via the documented user-teams join
- [x] Budget checks with warn/breach alerts
- [x] CLI: `collect`, `report`, `billing`, `budget-check`, `estimate`

## v0.2 -- Attribution & dashboards
- [ ] Streamlit dashboard (spend over time, per-team leaderboard, top users,
      acceptance rate)
- [ ] Slack/webhook alert delivery for budget breaches
- [ ] CSV export for finance
- [ ] Seat optimization report (inactive license holders to reclaim)
- [ ] Per-model burn analytics (which models/surfaces consume the pool)
- [ ] Spend forecasting vs. the pooled allowance

## v0.3 -- FinOps depth
- [ ] Warehouse sinks (BigQuery / Snowflake / Postgres)
- [ ] Multi-org rollup for enterprises with many orgs
- [ ] Anomaly detection (unusual spend spikes per user/team)
- [ ] ROI module: correlate usage with delivery metrics (acceptance rate,
      lines added per credit, review turnaround)
- [ ] Policy guardrails: per-team model allowlists with cost-impact preview

## Future ideas
- [ ] IDE plugin telemetry (opt-in) for finer-grained token accounting
- [ ] Chargeback invoicing integration (NetSuite/Stripe)
- [ ] Scheduled email digests for engineering leadership
