"""Configuration loading for copilot-usage-tracker."""

from __future__ import annotations

import os
from dataclasses import dataclass, field


@dataclass
class Settings:
    """Runtime settings, resolved from environment variables."""

    github_token: str = field(default_factory=lambda: os.environ.get("GITHUB_TOKEN", ""))
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

    def validate(self) -> None:
        if not self.github_token:
            raise ValueError("GITHUB_TOKEN is not set")
        if not self.enterprise and not self.org:
            raise ValueError(
                "Set COPILOT_ENTERPRISE or COPILOT_ORG to scope usage collection"
            )


def load_settings(policy=None) -> Settings:
    settings = Settings()
    if policy is not None and policy.network.api_base:
        settings.api_base = policy.network.api_base
    settings.validate()
    return settings
