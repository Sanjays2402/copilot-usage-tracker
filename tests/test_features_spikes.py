"""Tests for insights.spike_alerts — credit-spike anomaly detection."""

import pytest

from copilot_usage_tracker.insights import spike_alerts
from copilot_usage_tracker.store import UsageStore


@pytest.fixture()
def store(tmp_path):
    s = UsageStore(tmp_path / "spikes.db")
    # alice: 8 steady days ~100 credits, then a big spike on the latest day.
    for d in range(1, 8):
        s.upsert_user_day(
            f"2026-09-{d:02d}", "acme", 1, user_login="alice", ai_credits_used=100.0, interactions=5
        )
    s.upsert_user_day(
        "2026-09-08", "acme", 1, user_login="alice", ai_credits_used=500.0, interactions=25
    )
    # bob: same history, latest day only slightly elevated — no spike.
    for d in range(1, 8):
        s.upsert_user_day(
            f"2026-09-{d:02d}", "acme", 2, user_login="bob", ai_credits_used=100.0, interactions=5
        )
    s.upsert_user_day(
        "2026-09-08", "acme", 2, user_login="bob", ai_credits_used=150.0, interactions=6
    )
    # carol: big spike but too little history (5 days < min_history_days=7).
    for d in range(1, 5):
        s.upsert_user_day(
            f"2026-09-{d:02d}", "acme", 3, user_login="carol", ai_credits_used=10.0, interactions=1
        )
    s.upsert_user_day(
        "2026-09-05", "acme", 3, user_login="carol", ai_credits_used=500.0, interactions=20
    )
    # dave: big relative spike but latest day below min_credits.
    for d in range(1, 8):
        s.upsert_user_day(
            f"2026-09-{d:02d}", "acme", 4, user_login="dave", ai_credits_used=2.0, interactions=1
        )
    s.upsert_user_day(
        "2026-09-08", "acme", 4, user_login="dave", ai_credits_used=20.0, interactions=3
    )
    return s


def test_flags_spike_and_ignores_normal_user(store):
    alerts = spike_alerts(store, "2026-09", "acme")
    users = [a["user"] for a in alerts]
    assert "alice" in users
    assert "bob" not in users


def test_alert_fields(store):
    alerts = spike_alerts(store, "2026-09", "acme")
    alice = next(a for a in alerts if a["user"] == "alice")
    assert alice["latest_day"] == "2026-09-08"
    assert alice["latest_credits"] == pytest.approx(500.0)
    assert alice["trailing_avg"] == pytest.approx(100.0)
    assert alice["multiple"] == pytest.approx(5.0)


def test_requires_min_history_days(store):
    # carol's spike is on day 5 with only 5 daily rows -> ignored.
    alerts = spike_alerts(store, "2026-09", "acme")
    assert "carol" not in [a["user"] for a in alerts]


def test_requires_min_credits(store):
    # dave: 10x spike but latest day is only 20 credits < 50.
    alerts = spike_alerts(store, "2026-09", "acme")
    assert "dave" not in [a["user"] for a in alerts]


def test_sorted_by_multiple_desc(tmp_path):
    s = UsageStore(tmp_path / "sorted.db")
    for d in range(1, 8):
        s.upsert_user_day(f"2026-09-{d:02d}", "acme", 1, user_login="modest", ai_credits_used=100.0)
        s.upsert_user_day(f"2026-09-{d:02d}", "acme", 2, user_login="wild", ai_credits_used=100.0)
    s.upsert_user_day("2026-09-08", "acme", 1, user_login="modest", ai_credits_used=320.0)  # 3.2x
    s.upsert_user_day("2026-09-08", "acme", 2, user_login="wild", ai_credits_used=900.0)  # 9x
    alerts = spike_alerts(s, "2026-09", "acme")
    assert [a["user"] for a in alerts] == ["wild", "modest"]


def test_scope_filtering(store):
    # other scope should not see acme's spike.
    alerts = spike_alerts(store, "2026-09", "other")
    assert alerts == []


def test_empty_month_returns_empty(tmp_path):
    s = UsageStore(tmp_path / "empty.db")
    assert spike_alerts(s, "2026-09", "acme") == []
