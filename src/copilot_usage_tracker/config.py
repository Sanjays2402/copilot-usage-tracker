"""Configuration loading for copilot-usage-tracker."""

from __future__ import annotations

import os
from dataclasses import dataclass, field

from .auth import TokenNotFoundError, resolve_token


@dataclass
class Settings:
    """Runtime settings, resolved from environment variables and auth."""

    # Excluded from repr so the token can't leak into tracebacks/logs.
    github_token: str = field(default="", repr=False)
    token_source: str = field(default="")  # env | keyring | gh | prompt
    enterprise: str = field(default_factory=lambda: os.environ.get("COPILOT_ENTERPRISE", ""))
    org: str = field(default_factory=lambda: os.environ.get("COPILOT_ORG", ""))
    db_path: str = field(
        default_factory=lambda: os.environ.get("COPILOT_DB", "copilot_usage.db")
    )
    api_base: str = field(
        default_factory=lambda: os.environ.get(
            "COPILOT_API_BASE", "https://api.github.com"
        )
    )

    def validate(self, require_token: bool = True) -> None:
        if require_token and not self.github_token:
            raise TokenNotFoundError()
        if not self.enterprise and not self.org:
            raise ValueError(
                "Set COPILOT_ENTERPRISE or COPILOT_ORG to scope usage collection"
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
