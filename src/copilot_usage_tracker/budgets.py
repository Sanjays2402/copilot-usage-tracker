"""Budgets and spend alerts.

Enterprises define a monthly (or custom-period) dollar budget per scope --
whole enterprise, org, or team -- and ``check_budgets`` flags which scopes
are over budget or trending toward it. Alert delivery (Slack, email,
webhook) is intentionally left to the caller so this stays dependency-free.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Budget:
    scope: str  # e.g. "enterprise", "org:acme", "team:platform"
    limit_usd: float
    spent_usd: float = 0.0
    period: str = "monthly"
    alert_thresholds: tuple = (0.8, 1.0)  # warn at 80%, breach at 100%

    @property
    def utilization(self) -> float:
        return self.spent_usd / self.limit_usd if self.limit_usd else 0.0

    def status(self) -> str:
        u = self.utilization
        if u >= self.alert_thresholds[1]:
            return "breached"
        if u >= self.alert_thresholds[0]:
            return "warning"
        return "ok"


@dataclass
class BudgetAlert:
    scope: str
    status: str
    spent_usd: float
    limit_usd: float
    utilization: float
    message: str = field(default="")


def check_budgets(budgets: list[Budget]) -> list[BudgetAlert]:
    """Return alerts for budgets at warning level or breached."""
    alerts = []
    for b in budgets:
        status = b.status()
        if status == "ok":
            continue
        alerts.append(
            BudgetAlert(
                scope=b.scope,
                status=status,
                spent_usd=round(b.spent_usd, 2),
                limit_usd=b.limit_usd,
                utilization=round(b.utilization, 4),
                message=(
                    f"Copilot spend for {b.scope} is {status}: "
                    f"${b.spent_usd:,.2f} of ${b.limit_usd:,.2f} "
                    f"({b.utilization:.0%} of {b.period} budget)"
                ),
            )
        )
    return alerts
