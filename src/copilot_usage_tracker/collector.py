"""Collection layer for GitHub's Copilot usage metrics reports API.

The legacy inline-JSON endpoints (``GET .../copilot/usage``,
``GET .../copilot/metrics``) were retired on 2026-04-02. The current API is
report-based: each endpoint returns ``{"download_links": [...],
"report_day": "YYYY-MM-DD"}`` and the rows live in NDJSON files behind
time-limited signed URLs.

Also included: the AI-credit billing endpoint, which returns exact
per-user/per-model credit consumption (gross / allowance-covered / net
billed) straight from GitHub's billing system.
"""

from __future__ import annotations

import time
from typing import Any

import requests

from .audit import AuditLogger, AuditMixin
from .config import Settings

# Report names per scope, from the GitHub docs "REST API endpoints for
# Copilot usage metrics".
REPORTS = {
    "enterprise": {
        "entity_day": "enterprise-1-day",
        "entity_28d": "enterprise-28-day",
        "users_day": "users-1-day",
        "users_28d": "users-28-day",
        "user_teams_day": "user-teams-1-day",
        "repos_day": "repos-1-day",
    },
    "org": {
        "entity_day": "organization-1-day",
        "entity_28d": "organization-28-day",
        "users_day": "users-1-day",
        "users_28d": "users-28-day",
        "user_teams_day": "user-teams-1-day",
        "repos_day": "repos-1-day",
    },
}


class CopilotReportsClient(AuditMixin):
    """Client for the report-based Copilot usage metrics API."""

    def __init__(self, settings: Settings, audit: AuditLogger | None = None):
        self.settings = settings
        self.audit = audit
        self.session = requests.Session()
        self.session.headers.update(
            {
                "Accept": "application/vnd.github+json",
                "Authorization": f"Bearer {settings.github_token}",
                "X-GitHub-Api-Version": "2022-11-28",
            }
        )

    @property
    def _scope(self) -> str:
        if self.settings.enterprise:
            return "enterprise"
        return "org"

    @property
    def _base_path(self) -> str:
        if self.settings.enterprise:
            return f"/enterprises/{self.settings.enterprise}/copilot/metrics/reports"
        return f"/orgs/{self.settings.org}/copilot/metrics/reports"

    def _get(self, path: str, params: dict | None = None) -> Any:
        url = f"{self.settings.api_base}{path}"
        for _ in range(3):
            resp = self.session.get(url, params=params, timeout=60)
            self._audit("GET", resp.url, resp.status_code)
            if resp.status_code == 403 and "rate limit" in resp.text.lower():
                reset = int(resp.headers.get("X-RateLimit-Reset", time.time() + 60))
                time.sleep(max(reset - time.time(), 0) + 1)
                continue
            resp.raise_for_status()
            return resp.json()
        raise RuntimeError(f"GET {path} failed after retries")

    def report_links(self, report: str, day: str | None = None) -> tuple[list[str], str]:
        """Return (download_links, report_day) for a report.

        Pass ``day="latest"`` for the rolling 28-day reports, or
        ``day="YYYY-MM-DD"`` for single-day reports.
        """
        if day == "latest":
            path = f"{self._base_path}/{report}/latest"
            params = None
        else:
            path = f"{self._base_path}/{report}"
            params = {"day": day} if day else None
        payload = self._get(path, params)
        return payload.get("download_links", []), payload.get("report_day", day or "")

    def download_ndjson(self, url: str) -> list[dict]:
        """Download one NDJSON report file; one dict per line."""
        rows = []
        with self.session.get(url, timeout=120, stream=True) as resp:
            self._audit("GET", url, resp.status_code, note="ndjson download")
            resp.raise_for_status()
            for line in resp.iter_lines(decode_unicode=True):
                line = line.strip()
                if line:
                    import json

                    rows.append(json.loads(line))
        return rows

    def fetch_report(self, report: str, day: str | None = None) -> list[dict]:
        """Fetch a full report (all download links) as a list of rows."""
        links, _ = self.report_links(report, day)
        rows: list[dict] = []
        for link in links:
            rows.extend(self.download_ndjson(link))
        return rows

    # Convenience wrappers -------------------------------------------------
    def users_day(self, day: str) -> list[dict]:
        return self.fetch_report(REPORTS[self._scope]["users_day"], day)

    def entity_day(self, day: str) -> list[dict]:
        return self.fetch_report(REPORTS[self._scope]["entity_day"], day)

    def user_teams_day(self, day: str) -> list[dict]:
        return self.fetch_report(REPORTS[self._scope]["user_teams_day"], day)

    def repos_day(self, day: str) -> list[dict]:
        return self.fetch_report(REPORTS[self._scope]["repos_day"], day)


class BillingClient(AuditMixin):
    """Client for GitHub's AI-credit billing endpoint (enterprise scope).

    Returns exact billing figures: per-user, per-model ``usageItems`` with
    gross / allowance-covered (discount) / net-billed quantities and amounts.
    """

    def __init__(self, settings: Settings, audit: AuditLogger | None = None):
        if not settings.enterprise:
            raise ValueError("AI-credit billing endpoint requires COPILOT_ENTERPRISE")
        self.settings = settings
        self.audit = audit
        self.session = requests.Session()
        self.session.headers.update(
            {
                "Accept": "application/vnd.github+json",
                "Authorization": f"Bearer {settings.github_token}",
                "X-GitHub-Api-Version": "2022-11-28",
            }
        )

    def ai_credit_usage(
        self,
        year: int,
        month: int,
        day: int | None = None,
        user: str | None = None,
    ) -> list[dict]:
        """Fetch AI-credit usage items for a billing period.

        Endpoint: GET /enterprises/{enterprise}/settings/billing/ai_credit/usage
        """
        params: dict[str, Any] = {"year": year, "month": month}
        if day:
            params["day"] = day
        if user:
            params["user"] = user
        url = (
            f"{self.settings.api_base}/enterprises/{self.settings.enterprise}"
            f"/settings/billing/ai_credit/usage"
        )
        resp = self.session.get(url, params=params, timeout=60)
        self._audit("GET", resp.url, resp.status_code, note="ai-credit billing")
        resp.raise_for_status()
        payload = resp.json()
        if isinstance(payload, dict) and "usageItems" in payload:
            return payload["usageItems"]
        return payload if isinstance(payload, list) else []
