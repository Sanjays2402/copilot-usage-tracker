"""Tests for the API audit log."""

import json

from copilot_usage_tracker.audit import AuditLogger


def test_audit_log_writes_jsonl(tmp_path):
    path = tmp_path / "audit.jsonl"
    logger = AuditLogger(path)
    logger.log("GET", "https://api.github.com/enterprises/acme/copilot/metrics/reports"
                      "/users-1-day?day=2026-09-08", status=200)
    lines = path.read_text().strip().split("\n")
    assert len(lines) == 1
    record = json.loads(lines[0])
    assert record["method"] == "GET"
    assert record["host"] == "api.github.com"
    assert record["path"] == "/enterprises/acme/copilot/metrics/reports/users-1-day"
    assert record["params"] == {"day": "2026-09-08"}
    assert record["status"] == 200
    assert "ts" in record


def test_audit_log_drops_signed_url_tokens(tmp_path):
    path = tmp_path / "audit.jsonl"
    logger = AuditLogger(path)
    logger.log("GET", "https://objects.githubusercontent.com/report.ndjson"
                      "?sig=SECRET&se=1234&day=2026-09-08", status=200)
    record = json.loads(path.read_text().strip())
    # signed token params must not be retained; safe ones are
    assert record["params"] == {"day": "2026-09-08"}
    assert "SECRET" not in path.read_text()


def test_audit_log_never_records_auth(tmp_path):
    path = tmp_path / "audit.jsonl"
    logger = AuditLogger(path)
    logger.log("POST", "https://api.github.com/enterprises/acme/settings/billing/reports",
               status=201, note="billing report request")
    content = path.read_text()
    assert "Bearer" not in content
    assert "Authorization" not in content


def test_audit_disabled_no_file(tmp_path):
    path = tmp_path / "audit.jsonl"
    logger = AuditLogger(path, enabled=False)
    logger.log("GET", "https://api.github.com/x", status=200)
    assert not path.exists()


def test_audit_note_recorded(tmp_path):
    path = tmp_path / "audit.jsonl"
    logger = AuditLogger(path)
    logger.log("GET", "https://api.github.com/x", note="ndjson download")
    assert json.loads(path.read_text().strip())["note"] == "ndjson download"
