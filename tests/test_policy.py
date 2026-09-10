"""Tests for the enterprise policy layer."""

import pytest
import yaml

from copilot_usage_tracker.policy import (
    PRESETS,
    apply_to_session,
    load_policy,
    write_preset,
)


def test_load_policy_defaults_no_file(tmp_path, monkeypatch):
    monkeypatch.setenv("COPILOT_POLICY_FILE", str(tmp_path / "nonexistent.yaml"))
    for var in ("COPILOT_ANONYMIZE_USERS", "COPILOT_RETENTION_DAYS",
                "COPILOT_ALLOWED_SCOPES", "COPILOT_API_BASE"):
        monkeypatch.delenv(var, raising=False)
    policy = load_policy()
    assert policy.collection.collect_per_user is True
    assert policy.privacy.anonymize_users is False
    assert policy.privacy.retention_days == 0
    assert policy.audit.enabled is True
    assert policy.scope_allowed("anything") is True


def test_load_policy_from_file(tmp_path, monkeypatch):
    path = tmp_path / "policy.yaml"
    path.write_text(yaml.safe_dump({
        "collection": {"allowed_scopes": ["acme"], "collect_per_user": False},
        "privacy": {"anonymize_users": True, "user_salt": "s3cr3t",
                    "retention_days": 90, "drop_raw_json": True},
    }))
    monkeypatch.setenv("COPILOT_POLICY_FILE", str(path))
    policy = load_policy()
    assert policy.scope_allowed("acme") is True
    assert policy.scope_allowed("evilcorp") is False
    assert policy.collection.collect_per_user is False
    assert policy.privacy.anonymize_users is True
    assert policy.privacy.user_salt == "s3cr3t"
    assert policy.privacy.retention_days == 90
    assert policy.privacy.drop_raw_json is True


def test_env_overrides_file(tmp_path, monkeypatch):
    path = tmp_path / "policy.yaml"
    path.write_text(yaml.safe_dump({"privacy": {"anonymize_users": False}}))
    monkeypatch.setenv("COPILOT_POLICY_FILE", str(path))
    monkeypatch.setenv("COPILOT_ANONYMIZE_USERS", "1")
    monkeypatch.setenv("COPILOT_RETENTION_DAYS", "30")
    monkeypatch.setenv("COPILOT_ALLOWED_SCOPES", "acme,globex")
    policy = load_policy()
    assert policy.privacy.anonymize_users is True
    assert policy.privacy.retention_days == 30
    assert policy.collection.allowed_scopes == ["acme", "globex"]


def test_write_preset_strict(tmp_path):
    out = write_preset("strict", tmp_path / "policy.yaml")
    data = yaml.safe_load(out.read_text())
    assert data["privacy"]["anonymize_users"] is True
    assert data["privacy"]["drop_raw_json"] is True
    assert data["privacy"]["retention_days"] == 90
    assert len(data["privacy"]["user_salt"]) >= 16  # fresh salt generated
    # salts differ per generation
    out2 = write_preset("strict", tmp_path / "policy2.yaml")
    assert yaml.safe_load(out2.read_text())["privacy"]["user_salt"] != \
        data["privacy"]["user_salt"]


def test_write_preset_aggregate(tmp_path):
    out = write_preset("aggregate", tmp_path / "policy.yaml")
    data = yaml.safe_load(out.read_text())
    assert data["collection"]["collect_per_user"] is False


def test_write_preset_unknown(tmp_path):
    with pytest.raises(ValueError):
        write_preset("nope", tmp_path / "policy.yaml")


def test_presets_all_documented():
    from copilot_usage_tracker.policy import PRESET_DESCRIPTIONS
    assert set(PRESETS) == set(PRESET_DESCRIPTIONS)


def test_apply_to_session():
    import requests

    from copilot_usage_tracker.policy import NetworkPolicy, Policy

    session = requests.Session()
    policy = Policy(network=NetworkPolicy(proxy="http://proxy:8080",
                                          ca_bundle="/tmp/ca.pem"))
    apply_to_session(session, policy)
    assert session.proxies["https"] == "http://proxy:8080"
    assert session.verify == "/tmp/ca.pem"


def test_ensure_salt_stable_from_env(monkeypatch):
    monkeypatch.delenv("COPILOT_USER_SALT", raising=False)
    monkeypatch.setenv("COPILOT_POLICY_FILE", "/nonexistent-policy.yaml")
    policy = load_policy()
    monkeypatch.setenv("COPILOT_USER_SALT", "fixed-salt")
    assert policy.ensure_salt() == "fixed-salt"
    assert policy.ensure_salt() == "fixed-salt"  # stable, not regenerated
