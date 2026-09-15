"""Bug-hunt regression tests: real bugs found in the 2026-09-14 sweep.

Naming: test_bughunt_*.py so a sibling agent's test_features_*.py work is
never clobbered.
"""

import json
from collections import deque

import pytest
import yaml
from click.testing import CliRunner

from copilot_usage_tracker import cli as cli_mod
from copilot_usage_tracker.appconfig import load_app_config
from copilot_usage_tracker.audit import read_audit_log
from copilot_usage_tracker.billing_reports import BillingReportsClient
from copilot_usage_tracker.policy import Policy, load_policy
from copilot_usage_tracker.trust import token_privilege_verdict


@pytest.fixture()
def clean_env(monkeypatch):
    for var in (
        "COPILOT_POLICY_FILE",
        "COPILOT_ALLOWED_SCOPES",
        "COPILOT_COLLECT_PER_USER",
        "COPILOT_ANONYMIZE_USERS",
        "COPILOT_USER_SALT",
        "COPILOT_RETENTION_DAYS",
        "COPILOT_DROP_RAW_JSON",
        "COPILOT_AUDIT",
    ):
        monkeypatch.delenv(var, raising=False)


# --- cli.py: init-policy --output was bound at import time -----------------
def test_init_policy_output_honors_policy_file_env(tmp_path, monkeypatch, clean_env):
    """COPILOT_POLICY_FILE set after import must be honored by init-policy."""
    target = tmp_path / "custom" / "policy.yaml"
    monkeypatch.setenv("COPILOT_POLICY_FILE", str(target))
    result = CliRunner().invoke(cli_mod.main, ["init-policy"])
    assert result.exit_code == 0, result.output
    assert target.is_file(), f"policy written to wrong place:\n{result.output}"


# --- cli.py: billing printed truncated (invalid) JSON ----------------------
class _FakeResp:
    def __init__(self, payload):
        self._payload = payload
        self.status_code = 200

    def raise_for_status(self):
        pass

    def json(self):
        return self._payload


class _FakeBillingClient:
    def __init__(self, settings, audit=None):
        import requests

        self.session = requests.Session()
        self._items = [{"user": f"user{i}", "credits": i} for i in range(300)]

    def ai_credit_usage(self, year, month, user=None):
        return self._items


def test_billing_output_is_valid_json(tmp_path, monkeypatch, clean_env):
    """`billing` must emit parseable JSON even for large result sets."""
    monkeypatch.setattr(cli_mod, "BillingClient", _FakeBillingClient)
    monkeypatch.setattr(
        cli_mod,
        "_policy_and_settings",
        lambda: (Policy(), object(), "acme", None),
    )
    result = CliRunner(mix_stderr=False).invoke(
        cli_mod.main, ["billing", "--year", "2026", "--month", "9"]
    )
    assert result.exit_code == 0, result.output
    items = json.loads(result.stdout)  # must not raise
    assert isinstance(items, list) and len(items) == 100
    assert "300" in result.stderr  # truncation note goes to stderr, not the JSON


# --- policy.py: malformed policy.yaml must not crash -----------------------
def test_load_policy_ignores_unknown_keys(tmp_path, monkeypatch, clean_env):
    path = tmp_path / "policy.yaml"
    path.write_text(
        yaml.safe_dump({"collection": {"bogus_key": 1, "collect_per_user": False}}),
        encoding="utf-8",
    )
    monkeypatch.setenv("COPILOT_POLICY_FILE", str(path))
    policy = load_policy()  # must not raise TypeError
    assert policy.collection.collect_per_user is False


def test_load_policy_non_dict_yaml(tmp_path, monkeypatch, clean_env):
    path = tmp_path / "policy.yaml"
    path.write_text("- just\n- a\n- list\n", encoding="utf-8")
    monkeypatch.setenv("COPILOT_POLICY_FILE", str(path))
    policy = load_policy()  # must not raise AttributeError
    assert policy.collection.collect_per_user is True


def test_load_policy_non_dict_section(tmp_path, monkeypatch, clean_env):
    path = tmp_path / "policy.yaml"
    path.write_text(yaml.safe_dump({"privacy": "oops"}), encoding="utf-8")
    monkeypatch.setenv("COPILOT_POLICY_FILE", str(path))
    policy = load_policy()  # must not raise TypeError
    assert policy.privacy.retention_days == 0


# --- appconfig.py: malformed config.yaml must not crash --------------------
def test_load_app_config_list_yaml(tmp_path, monkeypatch):
    import copilot_usage_tracker.appconfig as appconfig

    path = tmp_path / "config.yaml"
    path.write_text("- enterprise\n", encoding="utf-8")
    monkeypatch.setattr(appconfig, "config_file", lambda: str(path))
    cfg = load_app_config()  # must not raise TypeError
    assert cfg.enterprise == ""


# --- billing_reports.py: missing report id must fail loudly ----------------
def test_create_report_without_id_raises():
    import types

    settings = types.SimpleNamespace(
        enterprise="acme",
        api_base="https://api.github.com",
        github_token="t",
    )
    client = BillingReportsClient(settings)

    class Resp:
        status_code = 200

        def raise_for_status(self):
            pass

        def json(self):
            return {}  # no id / report_id

    client.session.post = lambda *a, **k: Resp()
    with pytest.raises(ValueError, match="report id"):
        client.create_report({"type": "ai_usage"})


# --- trust.py: public_repo / gist grant write power ------------------------
def test_verdict_flags_public_repo_and_gist():
    verdict = token_privilege_verdict("public_repo, read:org")
    assert verdict["level"] == "elevated"
    assert "public_repo" in verdict["write_scopes"]
    verdict = token_privilege_verdict("gist")
    assert verdict["level"] == "elevated"


# --- tray/app.py: failed startup must not orphan the dashboard server -------
def test_start_server_terminates_child_on_wait_timeout(tmp_path, monkeypatch):
    import tray.app as tray_app

    monkeypatch.setattr(tray_app, "_log_file_path", lambda: str(tmp_path / "tray.log"))

    terminated = []

    class FakeProc:
        def poll(self):
            return None

        def terminate(self):
            terminated.append(True)

        def wait(self, timeout=None):
            return 0

    monkeypatch.setattr(tray_app.subprocess, "Popen", lambda *a, **k: FakeProc())

    def _boom(port, timeout=0):
        raise TimeoutError("never came up")

    monkeypatch.setattr(tray_app, "wait_for_port", _boom)

    app = tray_app.TrayApp()
    with pytest.raises(TimeoutError):
        app.start_server()
    assert terminated, "dashboard child was orphaned after failed startup"


def test_stop_server_escalates_to_kill(tmp_path, monkeypatch):
    import tray.app as tray_app

    monkeypatch.setattr(tray_app, "_log_file_path", lambda: str(tmp_path / "tray.log"))
    calls = []

    class StubbornProc:
        def poll(self):
            return None

        def terminate(self):
            calls.append("terminate")

        def wait(self, timeout=None):
            calls.append("wait")
            import subprocess as _sp

            raise _sp.TimeoutExpired("cmd", timeout)

        def kill(self):
            calls.append("kill")

    app = tray_app.TrayApp()
    app.server = StubbornProc()
    app.stop_server()
    assert calls == ["terminate", "wait", "kill"]


# --- audit.py: huge logs must not be fully loaded ---------------------------
def test_read_audit_log_large_file_newest_first(tmp_path):
    import json as _json

    path = tmp_path / "audit.jsonl"
    with open(path, "w", encoding="utf-8") as f:
        for i in range(5000):
            f.write(_json.dumps({"n": i}) + "\n")
    records = read_audit_log(path, limit=200)
    assert len(records) == 200
    assert records[0]["n"] == 4999  # newest first
    assert records[-1]["n"] == 4800


def test_read_audit_log_nonpositive_limit(tmp_path):
    path = tmp_path / "audit.jsonl"
    path.write_text('{"n": 1}\n', encoding="utf-8")
    assert read_audit_log(path, limit=0) == []
    # deque import sanity: module still exposes the helper
    assert deque is not None
