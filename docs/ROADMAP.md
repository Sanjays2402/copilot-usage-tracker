# Roadmap

## v0.1 -- Foundation (this release)
- [x] Report-based collector for the current Copilot usage metrics API
      (`users-1-day`, `entity-1-day`, `user-teams-1-day`, `repos-1-day`;
      NDJSON download flow)
- [x] AI-credit billing client (exact per-user/per-model figures from
      GitHub's billing API)
- [x] Billing reports export client (AI usage report CSV: per-model
      input/output/cache tokens + dollar amounts)
- [x] SQLite time-series store (per-user, per-scope, per-team, per-model
      daily rows)
- [x] AI-credit cost model (`PriceBook`: 1 credit = $0.01, pooled seat
      allowances, overage math)
- [x] Team attribution via the documented user-teams join
- [x] Budget checks with warn/breach alerts
- [x] Enterprise policy layer (`policy.py`): scope allowlists, per-user
      opt-out (aggregate mode), salted user pseudonymization, retention
      with auto-purge, corporate proxy/CA, GHES base URL, JSONL audit log
      of every API call; `init-policy --preset strict|standard|aggregate`,
      `purge`; `docs/ENTERPRISE.md` compliance guide
- [x] Streamlit dashboard (overview, teams, users, models & tokens, budgets)
- [x] Desktop tray app (Windows hidden icons / macOS menu bar): popup
      dashboard on click, background data collection, PyInstaller packaging
- [x] CLI: `collect`, `export-tokens`, `report`, `billing`, `budget-check`,
      `estimate`, `tray`

## v0.2 -- FinOps depth
- [ ] Slack/webhook alert delivery for budget breaches
- [ ] CSV export for finance
- [ ] Seat optimization report (inactive license holders to reclaim)
- [ ] Spend forecasting vs. the pooled allowance
- [ ] Scheduled email digests for engineering leadership

## v0.3 -- Scale
- [ ] Warehouse sinks (BigQuery / Snowflake / Postgres)
- [ ] Multi-org rollup for enterprises with many orgs
- [ ] Anomaly detection (unusual spend spikes per user/team)
- [ ] ROI module: correlate usage with delivery metrics (acceptance rate,
      lines added per credit, review turnaround)
- [ ] Policy guardrails: per-team model allowlists with cost-impact preview

## Future ideas
- [ ] IDE plugin telemetry (opt-in) for finer-grained token accounting
- [ ] Chargeback invoicing integration (NetSuite/Stripe)
