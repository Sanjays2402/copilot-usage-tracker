# Data sources

Everything this project collects comes from GitHub's official APIs. This page
documents the endpoints, what they return, and the billing facts the cost
math relies on. Verify against the linked docs before a production rollout --
GitHub changed this surface twice in 2026.

## Usage metrics: report-based API (current)

The legacy inline-JSON endpoints (`GET.../copilot/usage`,
`GET.../copilot/metrics`) were retired on **2026-04-02**.
The current API returns a `{"download_links": [...], "report_day":...}`
envelope; rows live in NDJSON files behind time-limited signed URLs:

| Report | Enterprise endpoint | Org endpoint |
|---|---|---|
| Entity 1-day | `GET /enterprises/{e}/copilot/metrics/reports/enterprise-1-day?day=YYYY-MM-DD` | `GET /orgs/{o}/copilot/metrics/reports/organization-1-day?day=YYYY-MM-DD` |
| Entity 28-day | `.../reports/enterprise-28-day/latest` | `.../reports/organization-28-day/latest` |
| Per-user 1-day | `GET /enterprises/{e}/copilot/metrics/reports/users-1-day?day=YYYY-MM-DD` | `GET /orgs/{o}/copilot/metrics/reports/users-1-day?day=YYYY-MM-DD` |
| Per-user 28-day | `.../reports/users-28-day/latest` | `.../reports/users-28-day/latest` |
| User-teams 1-day | `GET /enterprises/{e}/copilot/metrics/reports/user-teams-1-day?day=YYYY-MM-DD` | `GET /orgs/{o}/copilot/metrics/reports/user-teams-1-day?day=YYYY-MM-DD` |
| Repos 1-day | `GET /enterprises/{e}/copilot/metrics/reports/repos-1-day?day=YYYY-MM-DD` | `GET /orgs/{o}/copilot/metrics/reports/repos-1-day?day=YYYY-MM-DD` |

Key fields on per-user rows: `user_id`, `user_login`, `ai_credits_used`,
`user_initiated_interaction_count`, `code_generation_activity_count`,
`code_acceptance_activity_count`, `loc_suggested_to_add_sum`, `loc_added_sum`,
plus breakdown arrays (`totals_by_ide`, `totals_by_language_model`,
`totals_by_model_feature`,...).

Who can call these: enterprise owners, org admins, billing managers, or a
custom role with the View Enterprise Copilot Metrics permission.

### Team attribution join

There is no pre-aggregated team report. Join the daily user-teams report
with the same day's per-user report on `(user_id, day)` and aggregate by
`team_id`. Caveats from GitHub's docs, honored by `attribution.py`:
- Teams with **fewer than 5 seated Copilot users** are excluded from the
user-teams report.
- Multi-team users count toward *each* team; never sum team rows back into
an org/enterprise total.
- Always join daily-to-daily; never a 28-day activity report against a
single-day membership snapshot.

## Billing API: exact dollars

`GET /enterprises/{enterprise}/settings/billing/ai_credit/usage`
(`?user={login}&year=&month=&day=`) returns per-user, per-model
`usageItems` with gross / allowance-covered (`discount`) / net-billed
quantities **and** amounts -- exact billing figures, not estimates.

Seat assignments (who holds a license, incl. plan type) are available at
`GET /enterprises/{enterprise}/copilot/billing/seats` (and the org-level
equivalent) -- useful for the seat-reclamation report.

## Billing reports export: token-level data

No plain REST endpoint returns per-user input/output token counts. The
**AI usage report** export does: per-user, per-day, per-model rows with
`input`, `output`, `cache_read`, `cache_write` token columns plus
gross/discount/net dollar amounts. Access it programmatically:

- `POST /enterprises/{enterprise}/settings/billing/reports` to request
- `GET .../settings/billing/reports/{report_id}` to poll
- download the CSV when complete

`BillingReportsClient` in `billing_reports.py` implements this flow and
`copilot-usage export-tokens` stores the rows in `model_daily`. (The
per-user metrics NDJSON also carries `token_usage` with prompt/output
token sums, but only for the CLI and Copilot-app surfaces.)

## Billing model (since 2026-06-01)

GitHub bills metered Copilot usage in **AI Credits: 1 credit = $0.01
USD**, metered on the tokens each model
actually processes. Inline completions and next-edit suggestions stay free
and unmetered.

| Plan | Seat price | Included credits/seat/month (pooled) |
|---|---|---|
| Copilot Business | $19 | 1,900 |
| Copilot Enterprise | $39 | 3,900 |

Note: a promotional window boosted allowances (3,000 / 7,000) from June
through **September 1, 2026**, when they reverted to the standard
1,900 / 3,900. If your historical data
predates September 2026, re-baseline forecasts against the smaller pool.
