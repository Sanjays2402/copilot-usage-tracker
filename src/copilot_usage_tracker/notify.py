"""Outbound alert delivery over Slack/Teams-compatible webhooks.

Budget alerts computed by ``budgets.check_budgets`` can be pushed to a
chat channel with a single incoming-webhook URL -- no extra dependency,
just the standard library. The payload shape (``{"text": ...}``) works
with Slack incoming webhooks, Teams workflows, Discord, and most generic
chat receivers.
"""

from __future__ import annotations

import json
import urllib.request
from dataclasses import dataclass


@dataclass
class DeliveryResult:
    ok: bool
    status: int | None
    error: str = ""


def format_alert_message(scope: str, status: str, spent_usd: float,
                         limit_usd: float, utilization: float) -> str:
    """One-line human-readable alert, suitable for a chat message."""
    emoji = "🚨" if status == "breached" else "⚠️"
    return (
        f"{emoji} Copilot spend for {scope} is {status.upper()}: "
        f"${spent_usd:,.2f} of ${limit_usd:,.2f} "
        f"({utilization:.0%} of monthly budget)"
    )


def send_webhook(url: str, text: str, timeout: float = 10.0) -> DeliveryResult:
    """POST ``{"text": text}`` to an incoming-webhook URL."""
    payload = json.dumps({"text": text}).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            status = resp.status
            return DeliveryResult(ok=200 <= status < 300, status=status)
    except Exception as exc:  # noqa: BLE001 - surface delivery errors plainly
        return DeliveryResult(ok=False, status=None, error=str(exc))


def notify_budget_alerts(webhook_url: str, alerts: list) -> list[DeliveryResult]:
    """Send one chat message per budget alert; returns per-alert results."""
    results = []
    for alert in alerts:
        text = format_alert_message(
            alert.scope, alert.status, alert.spent_usd,
            alert.limit_usd, alert.utilization,
        )
        results.append(send_webhook(webhook_url, text))
    return results
