"""Per-user app configuration: the no-terminal story.

Enterprise/org scope, API base URL, and collection preferences live in a
YAML file under the OS user config dir (``~/.config`` on Linux,
``~/Library/Application Support`` on macOS, ``%APPDATA%`` on Windows).
The GitHub token is *not* kept here -- it lives in the OS keyring
(see ``auth.py``) or comes from the environment / ``gh`` CLI.

Environment variables (``COPILOT_ENTERPRISE``, ``COPILOT_ORG``,
``COPILOT_API_BASE``, ``COPILOT_DB``, ``COPILOT_POLICY_FILE``) always win,
so CI pipelines and power users keep working exactly as before. The GUI
(tray app + dashboard) reads and writes this file so end users never need
a terminal.
"""

from __future__ import annotations

import os
from dataclasses import asdict, dataclass

import platformdirs
import yaml

APP_NAME = "copilot-usage-tracker"
APP_AUTHOR = "Sanjays2402"


def config_dir() -> str:
    path = platformdirs.user_config_dir(APP_NAME, APP_AUTHOR)
    os.makedirs(path, exist_ok=True)
    return path


def data_dir() -> str:
    path = platformdirs.user_data_dir(APP_NAME, APP_AUTHOR)
    os.makedirs(path, exist_ok=True)
    return path


def config_file() -> str:
    return os.path.join(config_dir(), "config.yaml")


def default_db_path() -> str:
    return os.path.join(data_dir(), "copilot_usage.db")


def default_policy_file() -> str:
    return os.path.join(config_dir(), "policy.yaml")


@dataclass
class AppConfig:
    """User-level settings, edited through the GUI setup page."""

    enterprise: str = ""
    org: str = ""
    api_base: str = "https://api.github.com"
    with_teams: bool = True

    def scope(self) -> str:
        return self.enterprise or self.org


def load_app_config() -> AppConfig:
    path = config_file()
    data: dict = {}
    if os.path.isfile(path):
        with open(path, encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
    cfg = AppConfig()
    for key in ("enterprise", "org", "api_base", "with_teams"):
        if key in data and data[key] is not None:
            setattr(cfg, key, data[key])
    return cfg


def save_app_config(cfg: AppConfig) -> None:
    path = config_file()
    with open(path, "w", encoding="utf-8") as f:
        yaml.safe_dump(asdict(cfg), f, sort_keys=True)


def effective_scope(cfg: AppConfig | None = None) -> str:
    """Scope from env first, else the GUI config file."""
    if os.environ.get("COPILOT_ENTERPRISE"):
        return os.environ["COPILOT_ENTERPRISE"]
    if os.environ.get("COPILOT_ORG"):
        return os.environ["COPILOT_ORG"]
    return (cfg or load_app_config()).scope()


def is_configured(cfg: AppConfig | None = None) -> bool:
    return bool(effective_scope(cfg))


# Re-exported for convenience; keeps one import site for GUI code.
__all__ = [
    "AppConfig",
    "config_dir",
    "config_file",
    "data_dir",
    "default_db_path",
    "default_policy_file",
    "effective_scope",
    "is_configured",
    "load_app_config",
    "save_app_config",
]
