"""Tests for the billing-reports CSV parsing."""

from copilot_usage_tracker.billing_reports import parse_usage_csv

SAMPLE_CSV = """day,user,model,input,output,cache_read,cache_write,gross_amount,discount_amount,net_amount
2026-09-01,alice,claude-sonnet-4.5,"1,200,000",300000,50000,10000,18.50,10.00,8.50
2026-09-01,bob,gpt-5-mini,800000,200000,0,0,$12.00,12.00,0.00
"""


def test_parse_usage_csv_tokens():
    rows = parse_usage_csv(SAMPLE_CSV)
    assert len(rows) == 2
    assert rows[0]["input"] == 1200000
    assert rows[0]["output"] == 300000
    assert rows[0]["cache_read"] == 50000
    assert rows[0]["cache_write"] == 10000


def test_parse_usage_csv_amounts():
    rows = parse_usage_csv(SAMPLE_CSV)
    assert rows[0]["gross_amount"] == 18.50
    assert rows[0]["discount_amount"] == 10.00
    assert rows[0]["net_amount"] == 8.50
    assert rows[1]["gross_amount"] == 12.00  # $ prefix stripped
    assert rows[1]["net_amount"] == 0.00


def test_parse_usage_csv_passthrough():
    rows = parse_usage_csv(SAMPLE_CSV)
    assert rows[0]["user"] == "alice"
    assert rows[0]["model"] == "claude-sonnet-4.5"
    assert rows[0]["day"] == "2026-09-01"


def test_parse_usage_csv_empty():
    assert parse_usage_csv("day,user,model\n") == []
