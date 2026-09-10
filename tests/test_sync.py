"""Tests for in-process collection shared by CLI, GUI, and tray."""

import pytest

from copilot_usage_tracker import sync
from copilot_usage_tracker.appconfig import AppConfig, save_app_config
from copilot_usage_tracker.store import UsageStore
from copilot_usage_tracker.sync import run_collection, summary_line


class FakeClient:
    def __init__(self, settings, audit=None):
        import requests

        self.session = requests.Session()

    def users_day(self, day):
        return [
            {
                "user_id": 1,
                "user_login": "alice",
                "day": day,
                "ai_credits_used": 100.0,
                "user_initiated_interaction_count": 40,
                "loc_added_sum": 500,
            }
        ]

    def entity_day(self, day):
        return [{"ai_credits_used": 100.0}]

    def user_teams_day(self, day):
        return [{"user_id": 1, "day": day, "team_id": 7, "slug": "platform"}]


@pytest.fixture()
def collection_env(monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    monkeypatch.delenv("COPILOT_ENTERPRISE", raising=False)
    monkeypatch.delenv("COPILOT_ORG", raising=False)
    monkeypatch.setenv("COPILOT_DB", str(tmp_path / "test.db"))
    monkeypatch.setattr(sync, "CopilotReportsClient", FakeClient)
    monkeypatch.setattr("copilot_usage_tracker.config.resolve_token", lambda: ("tok", "env"))
    save_app_config(AppConfig(org="acme-corp"))
    yield tmp_path


def test_run_collection_stores_rows(collection_env):
    summary = run_collection("2026-09-08", with_teams=True)
    assert summary["users"] == 1
    assert summary["credits"] == 100.0
    assert summary["usd"] == 1.0
    assert summary["teams"] == 1

    store = UsageStore(collection_env / "test.db")
    assert store.monthly_credits("2026-09", scope="acme-corp") == 100.0
    assert store.monthly_active_users("2026-09", scope="acme-corp") == 1
    teams = store.team_totals("2026-09", scope="acme-corp")
    assert len(teams) == 1 and teams[0]["slug"] == "platform"
    store.close()


def test_run_collection_progress_callback(collection_env):
    messages = []
    run_collection("2026-09-08", progress=messages.append)
    assert messages and messages[-1] == "Done."


def test_summary_line(collection_env):
    summary = run_collection("2026-09-08", with_teams=False)
    line = summary_line(summary)
    assert "2026-09-08" in line and "100 credits" in line


def test_run_collection_refuses_disallowed_scope(collection_env, monkeypatch):
    from copilot_usage_tracker import policy as policy_mod

    real_load = policy_mod.load_policy

    def locked_load(path=None):
        p = real_load(path)
        p.collection.allowed_scopes = ["other-scope"]
        return p

    monkeypatch.setattr(policy_mod, "load_policy", locked_load)
    monkeypatch.setattr(sync, "load_policy", locked_load)
    with pytest.raises(ValueError, match="not in policy.yaml"):
        run_collection("2026-09-08")


def test_run_collection_needs_token(collection_env, monkeypatch):
    from copilot_usage_tracker.auth import TokenNotFoundError

    def _raise():
        raise TokenNotFoundError()

    monkeypatch.setattr("copilot_usage_tracker.config.resolve_token", _raise)
    with pytest.raises(TokenNotFoundError):
        run_collection("2026-09-08")
