# Architecture

`copilot-usage-tracker` is a small, boring-by-design pipeline: **collect → store → cost → report**.

```
┌──────────────┐      ┌──────────────┐      ┌──────────────┐      ┌──────────────┐
│ GitHub REST  │      │  collector.py│      │   store.py   │      │  tokens.py   │
│ Copilot APIs │─────▶│  (poll daily)│─────▶│ (SQLite ts)  │─────▶│ (cost model) │──▶ reports
└──────────────┘      └──────────────┘      └──────────────┘      └──────────────┘
                                                    │                     │
                                                    ▼                     ▼
                                             budgets.py (alerts)   CLI / dashboard
```

## Components

- **`collector.py`** — Thin HTTP client over GitHub's enterprise/org Copilot
  endpoints (`copilot/usage`, `copilot/metrics`, `copilot/seats`). No business
  logic; endpoint changes land here only. Handles rate-limit backoff.
- **`store.py`** — SQLite time series of daily snapshots. GitHub's APIs only
  retain a limited window, so the store is the system of record for trends.
  Swap for Postgres/DuckDB/BigQuery at scale (same `upsert_daily` shape).
- **`tokens.py`** — The FinOps heart. Converts line/request counts into
  estimated input/output tokens and applies the enterprise's price book
  (seat price, premium-request price, per-1k-token rates) to get dollars.
- **`budgets.py`** — Per-scope (enterprise/org/team) budgets with warn/breach
  thresholds. Alert *delivery* (Slack/email/webhook) is left to the operator.
- **`cli.py`** — `collect`, `report`, `budget-check`, `estimate` commands for
  cron jobs and ad-hoc analysis.

## Design principles

1. **Read-only against GitHub.** The tool never writes to the GitHub org.
2. **Price book is config, not code.** Every dollar figure comes from
   operator-supplied pricing; defaults are placeholders.
3. **Token counts are estimates, labeled as such.** GitHub exposes
   request/acceptance/line counts, not raw tokens; estimation ratios are
   documented and tunable per language.
4. **No vendor lock-in for storage or dashboards.** SQLite + a CLI today,
   warehouse + BI tomorrow.
