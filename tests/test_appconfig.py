"""Tests for the GUI app config (no-terminal onboarding)."""

import os

import pytest

from copilot_usage_tracker.appconfig import (
    AppConfig,
    effective_scope,
    is_configured,
    load_app_config,
    save_app_config,
)


@pytest.fixture()
def isolated_home(monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    monkeypatch.delenv("COPILOT_ENTERPRISE", raising=False)
    monkeypatch.delenv("COPILOT_ORG", raising=False)
    monkeypatch.delenv("COPILOT_API_BASE", raising=False)
    monkeypatch.delenv("COPILOT_DB", raising=False)
    yield tmp_path


def test_save_load_roundtrip(isolated_home):
    save_app_config(AppConfig(enterprise="acme", with_teams=False))
    cfg = load_app_config()
    assert cfg.enterprise == "acme"
    assert cfg.org == ""
    assert cfg.with_teams is False
    assert cfg.api_base == "https://api.github.com"


def test_not_configured_by_default(isolated_home):
    assert not is_configured()
    assert effective_scope() == ""


def test_configured_after_save(isolated_home):
    save_app_config(AppConfig(org="acme-corp"))
    assert is_configured()
    assert effective_scope() == "acme-corp"


def test_env_overrides_config_file(isolated_home, monkeypatch):
    save_app_config(AppConfig(org="from-file"))
    monkeypatch.setenv("COPILOT_ORG", "from-env")
    assert effective_scope() == "from-env"


def test_defaults_come_from_app_config(isolated_home):
    from copilot_usage_tracker.config import Settings

    save_app_config(AppConfig(enterprise="acme"))
    s = Settings()
    assert s.enterprise == "acme"
    assert s.db_path.startswith(str(isolated_home / "data"))
    assert s.db_path.endswith("copilot_usage.db")
    assert os.path.isdir(os.path.dirname(s.db_path))
    assert s.api_base == "https://api.github.com"


def test_scope_prefers_enterprise(isolated_home):
    save_app_config(AppConfig(enterprise="acme-ent", org="acme-org"))
    assert effective_scope() == "acme-ent"
