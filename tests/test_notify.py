"""Tests for chat webhook alert delivery."""

from copilot_usage_tracker.budgets import BudgetAlert
from copilot_usage_tracker.notify import (
    format_alert_message,
    notify_budget_alerts,
    send_webhook,
)


def test_format_alert_message_breached():
    msg = format_alert_message("acme", "breached", 1200.0, 1000.0, 1.2)
    assert "🚨" in msg
    assert "BREACHED" in msg
    assert "$1,200.00" in msg
    assert "$1,000.00" in msg
    assert "120%" in msg


def test_format_alert_message_warning():
    msg = format_alert_message("acme", "warning", 850.0, 1000.0, 0.85)
    assert "⚠️" in msg
    assert "WARNING" in msg


def test_send_webhook_success(monkeypatch):
    captured = {}

    class FakeResp:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    def fake_urlopen(req, timeout=None):
        captured["url"] = req.full_url
        captured["body"] = req.data.decode()
        captured["method"] = req.get_method()
        return FakeResp()

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    result = send_webhook("https://hooks.example/x", "hello")
    assert result.ok and result.status == 200
    assert captured["method"] == "POST"
    assert '"text": "hello"' in captured["body"]


def test_send_webhook_failure(monkeypatch):
    def boom(req, timeout=None):
        raise OSError("no route to host")

    monkeypatch.setattr("urllib.request.urlopen", boom)
    result = send_webhook("https://hooks.example/x", "hello")
    assert not result.ok
    assert result.status is None
    assert "no route" in result.error


def test_notify_budget_alerts(monkeypatch):
    sent = []

    def fake_send(url, text, timeout=10.0):
        sent.append((url, text))
        from copilot_usage_tracker.notify import DeliveryResult
        return DeliveryResult(ok=True, status=200)

    monkeypatch.setattr(
        "copilot_usage_tracker.notify.send_webhook", fake_send)
    alerts = [
        BudgetAlert(scope="acme", status="warning", spent_usd=850.0,
                    limit_usd=1000.0, utilization=0.85),
    ]
    results = notify_budget_alerts("https://hooks.example/x", alerts)
    assert len(results) == 1 and results[0].ok
    assert sent[0][0] == "https://hooks.example/x"
    assert "WARNING" in sent[0][1]
