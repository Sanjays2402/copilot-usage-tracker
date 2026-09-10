"""Configuration loading for copilot-usage-tracker.

Values resolve: environment variable -> GUI app config -> default.
The GUI (tray app + dashboard setup page) writes the app config file, so
end users never need a terminal; CI and power users keep using env vars.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field

from . import appconfig
from .auth import TokenNotFoundError, resolve_token


def _env_or_cfg(env_name: str, attr: str, default: str = "") -> str:
    value = os.environ.get(env_name)
    if value:
        return value
    return getattr(appconfig.load_app_config(), attr, "") or default


@dataclass
class Settings:
    """Runtime settings, resolved from environment variables and app config."""

    # Excluded from repr so the token can't leak into tracebacks/logs.
    github_token: str = field(default="", repr=False)
    token_source: str = field(default="")  # env | keyring | gh | prompt
    enterprise: str = field(
        default_factory=lambda: _env_or_cfg("COPILOT_ENTERPRISE", "enterprise")
    )
    org: str = field(default_factory=lambda: _env_or_cfg("COPILOT_ORG", "org"))
    db_path: str = field(
        default_factory=lambda: os.environ.get("COPILOT_DB")
        or appconfig.default_db_path()
    )
    api_base: str = field(
        default_factory=lambda: _env_or_cfg(
            "COPILOT_API_BASE", "api_base", "https://api.github.com"
        )
    )

    def validate(self, require_token: bool = True) -> None:
        if require_token and not self.github_token:
            raise TokenNotFoundError()
        if not self.enterprise and not self.org:
            raise ValueError(
                "No scope configured. Run the app and complete setup, "
                "or set COPILOT_ENTERPRISE / COPILOT_ORG."
            )


def load_settings(policy=None, require_token: bool = True) -> Settings:
    settings = Settings()
    if policy is not None and policy.network.api_base:
        settings.api_base = policy.network.api_base
    if require_token:
        token, source = resolve_token()
        settings.github_token = token
        settings.token_source = source
    settings.validate(require_token=require_token)
    return settings
