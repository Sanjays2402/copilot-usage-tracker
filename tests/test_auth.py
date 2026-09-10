"""Tests for the GitHub token handling."""

import pytest

from copilot_usage_tracker import auth
from copilot_usage_tracker.auth import (
    TokenNotFoundError,
    mask_token,
    prompt_token,
    resolve_token,
)
from copilot_usage_tracker.config import Settings, load_settings


@pytest.fixture(autouse=True)
def clean_auth(monkeypatch):
    auth.reset_cache()
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    # isolate from the developer's real keyring / gh session
    monkeypatch.setattr(auth, "_from_keyring", lambda: None)
    monkeypatch.setattr(auth, "_from_gh_cli", lambda: None)
    yield
    auth.reset_cache()


def test_resolve_from_env(monkeypatch):
    monkeypatch.setenv("GITHUB_TOKEN", "ghp_envtoken1234")
    token, source = resolve_token()
    assert (token, source) == ("ghp_envtoken1234", "env")


def test_env_wins_over_keyring(monkeypatch):
    monkeypatch.setenv("GITHUB_TOKEN", "env-token")
    monkeypatch.setattr(auth, "_from_keyring", lambda: "keyring-token")
    token, source = resolve_token()
    assert (token, source) == ("env-token", "env")


def test_resolve_from_keyring(monkeypatch):
    monkeypatch.setattr(auth, "_from_keyring", lambda: "keyring-token-1234")
    token, source = resolve_token()
    assert (token, source) == ("keyring-token-1234", "keyring")


def test_resolve_from_gh_cli(monkeypatch):
    monkeypatch.setattr(auth, "_from_gh_cli", lambda: "gh-cli-token")
    token, source = resolve_token()
    assert (token, source) == ("gh-cli-token", "gh")


def test_resolve_none_raises():
    with pytest.raises(TokenNotFoundError) as excinfo:
        resolve_token()
    assert "copilot-usage login" in str(excinfo.value)


def test_resolve_cached_per_process(monkeypatch):
    calls = []
    monkeypatch.setenv("GITHUB_TOKEN", "tok")
    orig = auth._from_env
    monkeypatch.setattr(auth, "_from_env",
                        lambda: calls.append(1) or orig())
    assert resolve_token()[0] == "tok"
    assert resolve_token()[0] == "tok"
    assert len(calls) == 1  # looked up once, then served from memory


def test_mask_token():
    assert mask_token("ghp_abcdef123456") == "ghp_…3456"
    assert mask_token("short") == "****"


def test_prompt_token_strips(monkeypatch):
    monkeypatch.setattr("getpass.getpass", lambda _: "  mytoken  \n")
    assert prompt_token() == "mytoken"


def test_token_hidden_from_repr():
    settings = Settings(github_token="supersecrettoken123")
    assert "supersecrettoken123" not in repr(settings)


def test_load_settings_offline_needs_no_token(monkeypatch):
    monkeypatch.setenv("COPILOT_ORG", "acme")
    settings = load_settings(require_token=False)
    assert settings.github_token == ""
    assert settings.org == "acme"


def test_load_settings_online_needs_token(monkeypatch):
    monkeypatch.setenv("COPILOT_ORG", "acme")
    with pytest.raises(TokenNotFoundError):
        load_settings(require_token=True)


def test_load_settings_records_source(monkeypatch):
    monkeypatch.setenv("GITHUB_TOKEN", "tok1234567890")
    monkeypatch.setenv("COPILOT_ORG", "acme")
    settings = load_settings()
    assert settings.token_source == "env"
    assert settings.github_token == "tok1234567890"
