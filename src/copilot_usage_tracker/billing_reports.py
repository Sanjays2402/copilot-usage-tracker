"""Client for GitHub's billing reports export API.

This is the only server-side source of per-user / per-day / per-model
**token-level** data: the AI usage report CSV carries ``input``, ``output``,
``cache_read`` and ``cache_write`` token columns plus gross / discount / net
dollar amounts.

Flow:
    POST /enterprises/{enterprise}/settings/billing/reports
      -> poll GET .../settings/billing/reports/{report_id}
      -> download the CSV when complete -> parse rows.

The exact POST payload schema should be verified against GitHub's current
"billing reports" docs; ``create_report`` passes the payload through so the
operator can match the docs without a code change.
"""

from __future__ import annotations

import csv
import io
import time
from typing import Any

import requests

from .audit import AuditLogger, AuditMixin
from .config import Settings

TOKEN_COLUMNS = ("input", "output", "cache_read", "cache_write")
AMOUNT_COLUMNS = ("gross_amount", "discount_amount", "net_amount")


class BillingReportsClient(AuditMixin):
    """Export-API client (enterprise scope)."""

    def __init__(self, settings: Settings, audit: AuditLogger | None = None):
        if not settings.enterprise:
            raise ValueError("Billing reports export requires COPILOT_ENTERPRISE")
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
        self._base = (
            f"{settings.api_base}/enterprises/{settings.enterprise}"
            "/settings/billing/reports"
        )

    def create_report(self, payload: dict) -> str:
        """Request a report; returns the report id."""
        resp = self.session.post(self._base, json=payload, timeout=60)
        self._audit("POST", self._base, resp.status_code,
                    note=f"billing report request: {payload.get('type')}")
        resp.raise_for_status()
        data = resp.json()
        return data.get("id") or data.get("report_id")

    def report_status(self, report_id: str) -> dict:
        url = f"{self._base}/{report_id}"
        resp = self.session.get(url, timeout=60)
        self._audit("GET", url, resp.status_code, note="billing report poll")
        resp.raise_for_status()
        return resp.json()

    def wait_for_report(self, report_id: str, timeout_s: int = 600) -> str:
        """Poll until the report is ready; returns the download URL."""
        deadline = time.time() + timeout_s
        while time.time() < deadline:
            status = self.report_status(report_id)
            state = str(status.get("status", "")).lower()
            if state in ("complete", "completed", "ready", "succeeded"):
                url = status.get("download_url") or status.get("url")
                if not url:
                    raise RuntimeError(f"Report {report_id} complete but no download URL")
                return url
            if state in ("failed", "error", "cancelled"):
                raise RuntimeError(f"Report {report_id} failed: {status}")
            time.sleep(15)
        raise TimeoutError(f"Report {report_id} not ready after {timeout_s}s")

    def download_csv(self, url: str) -> list[dict]:
        """Download and parse the report CSV into normalized row dicts."""
        resp = self.session.get(url, timeout=300)
        self._audit("GET", url, resp.status_code, note="billing report csv download")
        resp.raise_for_status()
        return parse_usage_csv(resp.text)


def _to_int(value: Any) -> int:
    try:
        return int(float(str(value).strip().replace(",", "")))
    except (ValueError, TypeError, AttributeError):
        return 0


def _to_float(value: Any) -> float:
    try:
        return float(str(value).strip().replace(",", "").lstrip("$"))
    except (ValueError, TypeError, AttributeError):
        return 0.0


def parse_usage_csv(text: str) -> list[dict]:
    """Parse an AI usage report CSV into normalized rows.

    Token columns become ints, amount columns become floats; every other
    column is passed through as-is.
    """
    rows: list[dict] = []
    reader = csv.DictReader(io.StringIO(text))
    for raw in reader:
        row = dict(raw)
        for col in TOKEN_COLUMNS:
            if col in row:
                row[col] = _to_int(row[col])
        for col in AMOUNT_COLUMNS:
            if col in row:
                row[col] = _to_float(row[col])
        rows.append(row)
    return rows
