"""AI-credit cost modeling.

Since 2026-06-01 GitHub bills metered Copilot usage in **AI Credits**:
1 credit = $0.01 USD. Per-user usage reports carry ``ai_credits_used`` and
the billing API returns exact per-model credit consumption, so dollar costs
here are *computed*, not estimated.

Plan reference (post 2026-09-01 promo window):
- Copilot Business:   $19/seat/month, 1,900 included credits per seat (pooled)
- Copilot Enterprise: $39/seat/month, 3,900 included credits per seat (pooled)
Inline completions and next-edit suggestions are free and unmetered.

``estimate_tokens_from_lines`` remains for what-if / forecasting scenarios
only -- it is an approximation and never feeds the billing math.
"""

from __future__ import annotations

from dataclasses import dataclass

#: Fixed GitHub conversion: 1 AI credit = $0.01.
CREDIT_USD = 0.01

#: Included monthly credits per seat, pooled across the org/enterprise.
PLAN_DEFAULTS = {
    "business": {"seat_price": 19.0, "included_credits_per_seat": 1900.0},
    "enterprise": {"seat_price": 39.0, "included_credits_per_seat": 3900.0},
}


def credits_to_usd(credits: float) -> float:
    """Convert AI credits to dollars at GitHub's fixed 1c rate."""
    return credits * CREDIT_USD


@dataclass
class PriceBook:
    """An enterprise's Copilot price book.

    Attributes:
        plan: "business" or "enterprise" (sets defaults; override freely).
        seat_price_monthly: flat per-seat monthly price.
        included_credits_per_seat: monthly credits bundled per seat (pooled).
        overage_allowed: whether spend beyond the pooled allowance is billed
            (otherwise usage is capped and the overage is $0 but throttled).
    """

    plan: str = "business"
    seat_price_monthly: float = 19.0
    included_credits_per_seat: float = 1900.0
    overage_allowed: bool = False

    @classmethod
    def for_plan(cls, plan: str, overage_allowed: bool = False) -> PriceBook:
        defaults = PLAN_DEFAULTS[plan.lower()]
        return cls(
            plan=plan.lower(),
            seat_price_monthly=defaults["seat_price"],
            included_credits_per_seat=defaults["included_credits_per_seat"],
            overage_allowed=overage_allowed,
        )

    def pooled_allowance(self, seats: int) -> float:
        return seats * self.included_credits_per_seat

    def monthly_cost(self, seats: int, credits_used: float) -> dict:
        """Dollar breakdown for a billing month."""
        seat_cost = seats * self.seat_price_monthly
        allowance = self.pooled_allowance(seats)
        overage_credits = max(0.0, credits_used - allowance)
        overage_cost = credits_to_usd(overage_credits) if self.overage_allowed else 0.0
        return {
            "plan": self.plan,
            "seats": seats,
            "seat_cost_usd": round(seat_cost, 2),
            "credits_used": credits_used,
            "included_credits": allowance,
            "overage_credits": round(overage_credits, 2),
            "overage_cost_usd": round(overage_cost, 2),
            "total_cost_usd": round(seat_cost + overage_cost, 2),
            "utilization": round(credits_used / allowance, 4) if allowance else 0.0,
        }


# --- Token estimation (forecasting only) -----------------------------------

#: Rough industry average for code: ~4 characters per token.
DEFAULT_CHARS_PER_TOKEN = 4.0


def estimate_tokens_from_lines(
    lines: int,
    chars_per_token: float = DEFAULT_CHARS_PER_TOKEN,
    avg_line_length: float = 40.0,
) -> int:
    """Approximate token count from lines of code (forecasting only).

    ``avg_line_length`` is the assumed mean line length in characters
    (tune per language; 40 is a reasonable default for mixed code).
    """
    if lines <= 0:
        return 0
    return int(lines * avg_line_length / chars_per_token)
