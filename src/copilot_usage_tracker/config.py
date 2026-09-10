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
    api_base: str = "https://api.github.com"

    def validate(self) -> None:
        if not self.github_token:
            raise ValueError("GITHUB_TOKEN is not set")
        if not self.enterprise and not self.org:
            raise ValueError(
                "Set COPILOT_ENTERPRISE or COPILOT_ORG to scope usage collection"
            )


def load_settings() -> Settings:
    settings = Settings()
    settings.validate()
    return settings
