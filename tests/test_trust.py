"""Tests for the trust & transparency helpers (Security tab)."""

from copilot_usage_tracker.store import UsageStore
from copilot_usage_tracker.trust import (
    data_inventory,
    network_summary,
    token_privilege_verdict,
)


def test_verdict_elevated_on_write_scopes():
    v = token_privilege_verdict("read:org, write:org, repo")
    assert v["level"] == "elevated"
    assert "write:org" in v["write_scopes"]
    assert "repo" in v["write_scopes"]
    assert "read:org" not in v["write_scopes"]


def test_verdict_least_privilege():
    v = token_privilege_verdict("read:org read:enterprise")
    assert v["level"] == "least-privilege"
    assert v["write_scopes"] == []


def test_verdict_unknown_without_scopes():
    for scopes in (None, "", "   "):
        v = token_privilege_verdict(scopes)
        assert v["level"] == "unknown"
        assert "fine-grained" in v["message"]


def test_data_inventory_counts_rows(tmp_path):
    s = UsageStore(tmp_path / "inv.db")
    s.upsert_user_day("2026-09-01", "org", 1, credits=10.0)
    s.upsert_scope_day("2026-09-01", "org", "organization", credits=10.0)
    inv = {r["table"]: r for r in data_inventory(s)}
    assert inv["user_daily"]["rows"] == 1
    assert inv["scope_daily"]["rows"] == 1
    assert inv["model_daily"]["rows"] == 0
    assert all(r["contents"] for r in inv.values())
    s.close()


def test_network_summary_read_only():
    recs = [
        {"method": "GET", "host": "api.github.com"},
        {"method": "get", "host": "api.github.com"},
    ]
    net = network_summary(recs, "https://api.github.com")
    assert net["read_only"] and net["local_only"]
    assert net["total_requests"] == 2
    assert net["non_get_requests"] == 0


def test_network_summary_flags_writes_and_third_parties():
    recs = [
        {"method": "GET", "host": "api.github.com"},
        {"method": "POST", "host": "hooks.slack.com"},
    ]
    net = network_summary(recs, "https://api.github.com")
    assert not net["read_only"] and not net["local_only"]
    assert net["non_get_requests"] == 1
    assert net["third_party_hosts"] == ["hooks.slack.com"]
