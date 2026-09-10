# Architecture

`copilot-usage-tracker` is a small, boring-by-design pipeline: **collect → store → cost → report**.

```
┌──────────────┐      ┌──────────────┐      ┌──────────────┐      ┌──────────────┐
│ GitHub report│      │ collector.py │      │   store.py   │      │  tokens.py   │
│ APIs (NDJSON)│─────▶│ (poll daily) │─────▶│ (SQLite ts)  │─────▶│ (cost model) │──▶ reports
└──────────────┘      └──────────────┘      └──────────────┘      └──────────────┘
┌──────────────┐      ┌──────────────┐             │                     ▲
│ Billing rpt  │      │billing_repor │─────────────┘                     │
│ export (CSV) │─────▶│ ts.py (tokens│──▶ model_daily                    │
└──────────────┘      └──────────────┘                                   │
                                                  insights.py (pure aggs)┘
                                                        │
                                                        ▼
                                              dashboard/app.py (Streamlit)
```

## Components

- **collector.py** — Thin HTTP client over GitHub's report-based Copilot
  metrics endpoints (`users-1-day`, `entity-1-day`, `user-teams-1-day`,
  `repos-1-day`) plus the AI-credit billing endpoint. No business logic;
  endpoint changes land here only. Handles rate-limit backoff.
- **billing_reports.py** — Client for the billing reports export API
  (request → poll → download CSV) and the CSV parser. This is the only
  server-side source of per-model input/output/cache token counts.
- **attribution.py** — Team-level rollups via GitHub's documented
  user-teams join (honors the 5-seat threshold and multi-team rules).
- **store.py** — SQLite time series of daily snapshots: per-user rows,
  per-scope and per-team rollups, and per-model token rows. GitHub's APIs
  only retain a limited window, so the store is the system of record for
  trends. Swap for Postgres/DuckDB/BigQuery at scale.
- **tokens.py** — The FinOps heart. Converts AI credits to dollars at
  GitHub's fixed 1¢ rate and applies the enterprise's price book (seat
  price, pooled allowance, overage policy). Token-estimation helpers are
  for what-if forecasting only.
- **budgets.py** — Per-scope (enterprise/org/team) budgets with warn/breach
  thresholds. Alert *delivery* (Slack/email/webhook) is left to the operator.
- **insights.py** — Pure aggregation helpers (KPIs, daily series, team
  leaderboard, model breakdown) shared by the CLI and the dashboard;
  trivially testable, no Streamlit dependency.
- **cli.py** — `collect`, `export-tokens`, `report`, `billing`,
  `budget-check`, `estimate` commands for cron jobs and ad-hoc analysis.
- **dashboard/app.py** — Streamlit app (Overview, Teams, Users,
  Models & Tokens, Budgets tabs) over the SQLite store.

## Design principles

1. **Read-only against GitHub.** The tool never writes to the GitHub org.
2. **Price book is config, not code.** Every dollar figure comes from
   operator-supplied pricing; defaults track GitHub's published plans.
3. **Dollars are computed, tokens are measured.** Credit and billing APIs
   give exact dollar figures; the export API gives measured token counts.
   Line-based token *estimation* is labeled as such and never feeds
   billing math.
4. **No vendor lock-in for storage or dashboards.** SQLite + Streamlit
   today, warehouse + BI tomorrow.
