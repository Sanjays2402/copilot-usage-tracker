"""Enterprise policy-as-code: adapt the tracker to company rules.

A ``policy.yaml`` lets compliance / IT teams declare what's allowed:

- which scopes may be collected (allowlist)
- whether per-user rows are collected at all
- whether user identities are pseudonymized
- how long data is retained (auto-purge)
- network controls (proxy, corporate CA bundle, GHES base URL)
- audit logging of every GitHub API call

Generate a starter file with ``copilot-usage init-policy --preset strict``.
Environment variables override file values (useful in CI/containers).
"""

from __future__ import annotations

import os
import secrets
from dataclasses import asdict, dataclass, field
from pathlib import Path

import yaml


def _env_bool(name: str) -> bool | None:
    val = os.environ.get(name)
    if val is None:
        return None
    return val.strip().lower() in ("1", "true", "yes", "on")


def _env_int(name: str) -> int | None:
    val = os.environ.get(name)
    if val is None:
        return None
    try:
        return int(val)
    except ValueError:
        return None


@dataclass
class CollectionPolicy:
    allowed_scopes: list = field(default_factory=list)  # empty = configured scope only
    collect_per_user: bool = True


@dataclass
class NetworkPolicy:
    proxy: str = ""
    ca_bundle: str = ""
    api_base: str = ""  # GitHub Enterprise Server, e.g. https://ghe.corp/api/v3


@dataclass
class PrivacyPolicy:
    anonymize_users: bool = False
    user_salt: str = ""
    retention_days: int = 0  # 0 = keep forever; N = auto-purge rows older than N days
    drop_raw_json: bool = False


@dataclass
class AuditPolicy:
    enabled: bool = True
    path: str = str(Path.home() / ".copilot-usage-tracker" / "audit.jsonl")


@dataclass
class Policy:
    collection: CollectionPolicy = field(default_factory=CollectionPolicy)
    network: NetworkPolicy = field(default_factory=NetworkPolicy)
    privacy: PrivacyPolicy = field(default_factory=PrivacyPolicy)
    audit: AuditPolicy = field(default_factory=AuditPolicy)

    def ensure_salt(self) -> str:
        """Return the pseudonymization salt, generating one if needed.

        Note: a generated salt is NOT persisted -- pass a stable salt via
        policy.yaml or COPILOT_USER_SALT or pseudonyms will churn between runs.
        """
        if not self.privacy.user_salt:
            self.privacy.user_salt = (
                os.environ.get("COPILOT_USER_SALT") or secrets.token_hex(16)
            )
        return self.privacy.user_salt

    def scope_allowed(self, scope: str) -> bool:
        if not self.collection.allowed_scopes:
            return True
        return scope in self.collection.allowed_scopes


PRESETS: dict = {
    "standard": {
        "collection": {"allowed_scopes": [], "collect_per_user": True},
        "network": {"proxy": "", "ca_bundle": "", "api_base": ""},
        "privacy": {
            "anonymize_users": False, "user_salt": "", "retention_days": 365,
            "drop_raw_json": False,
        },
        "audit": {"enabled": True,
                  "path": str(Path.home() / ".copilot-usage-tracker" / "audit.jsonl")},
    },
    "strict": {
        "collection": {"allowed_scopes": [], "collect_per_user": True},
        "network": {"proxy": "", "ca_bundle": "", "api_base": ""},
        "privacy": {
            "anonymize_users": True, "user_salt": "", "retention_days": 90,
            "drop_raw_json": True,
        },
        "audit": {"enabled": True,
                  "path": str(Path.home() / ".copilot-usage-tracker" / "audit.jsonl")},
    },
    "aggregate": {
        "collection": {"allowed_scopes": [], "collect_per_user": False},
        "network": {"proxy": "", "ca_bundle": "", "api_base": ""},
        "privacy": {
            "anonymize_users": False, "user_salt": "", "retention_days": 180,
            "drop_raw_json": True,
        },
        "audit": {"enabled": True,
                  "path": str(Path.home() / ".copilot-usage-tracker" / "audit.jsonl")},
    },
}

PRESET_DESCRIPTIONS = {
    "standard": "per-user collection, 1-year retention, audit on",
    "strict": "pseudonymized users, no raw payloads, 90-day retention, audit on",
    "aggregate": "no per-user rows at all (team/scope totals only), 180-day retention",
}


def default_policy_path() -> Path:
    return Path(os.environ.get("COPILOT_POLICY_FILE", "policy.yaml")).expanduser()


def _merge(base: dict, override: dict) -> dict:
    for key, val in override.items():
        if isinstance(val, dict) and isinstance(base.get(key), dict):
            _merge(base[key], val)
        else:
            base[key] = val
    return base


def _apply_env_overrides(data: dict) -> dict:
    data = _merge(data, {})
    collection, network, privacy, audit = (
        data.setdefault("collection", {}),
        data.setdefault("network", {}),
        data.setdefault("privacy", {}),
        data.setdefault("audit", {}),
    )
    if os.environ.get("COPILOT_ALLOWED_SCOPES"):
        collection["allowed_scopes"] = [
            s.strip() for s in os.environ["COPILOT_ALLOWED_SCOPES"].split(",") if s.strip()
        ]
    val = _env_bool("COPILOT_COLLECT_PER_USER")
    if val is not None:
        collection["collect_per_user"] = val
    if os.environ.get("COPILOT_PROXY"):
        network["proxy"] = os.environ["COPILOT_PROXY"]
    if os.environ.get("COPILOT_CA_BUNDLE"):
        network["ca_bundle"] = os.environ["COPILOT_CA_BUNDLE"]
    if os.environ.get("COPILOT_API_BASE"):
        network["api_base"] = os.environ["COPILOT_API_BASE"]
    val = _env_bool("COPILOT_ANONYMIZE_USERS")
    if val is not None:
        privacy["anonymize_users"] = val
    if os.environ.get("COPILOT_USER_SALT"):
        privacy["user_salt"] = os.environ["COPILOT_USER_SALT"]
    val = _env_int("COPILOT_RETENTION_DAYS")
    if val is not None:
        privacy["retention_days"] = val
    val = _env_bool("COPILOT_DROP_RAW_JSON")
    if val is not None:
        privacy["drop_raw_json"] = val
    val = _env_bool("COPILOT_AUDIT")
    if val is not None:
        audit["enabled"] = val
    return data


def _dict_to_policy(data: dict) -> Policy:
    return Policy(
        collection=CollectionPolicy(**data.get("collection", {})),
        network=NetworkPolicy(**data.get("network", {})),
        privacy=PrivacyPolicy(**data.get("privacy", {})),
        audit=AuditPolicy(**data.get("audit", {})),
    )


def load_policy(path: str | Path | None = None) -> Policy:
    """Load policy.yaml if present, else defaults; env vars always win."""
    policy_path = Path(path).expanduser() if path else default_policy_path()
    data: dict = {}
    if policy_path.is_file():
        with policy_path.open(encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
    return _dict_to_policy(_apply_env_overrides(data))


def policy_to_dict(policy: Policy) -> dict:
    return asdict(policy)


def write_preset(preset: str, path: str | Path) -> Path:
    """Write a preset policy file with a fresh pseudonymization salt."""
    if preset not in PRESETS:
        raise ValueError(f"unknown preset {preset!r}; choose from {sorted(PRESETS)}")
    import copy

    data = copy.deepcopy(PRESETS[preset])
    data["privacy"]["user_salt"] = secrets.token_hex(16)
    out = Path(path).expanduser()
    out.parent.mkdir(parents=True, exist_ok=True)
    header = (
        "# copilot-usage-tracker enterprise policy "
        f"(preset: {preset} -- {PRESET_DESCRIPTIONS[preset]})\n"
        "# See docs/ENTERPRISE.md for the full reference.\n"
    )
    with out.open("w", encoding="utf-8") as f:
        f.write(header)
        yaml.safe_dump(data, f, sort_keys=False)
    return out


def apply_to_session(session, policy: Policy) -> None:
    """Apply network policy (proxy, corporate CA) to a requests session."""
    if policy.network.proxy:
        session.proxies = {"http": policy.network.proxy, "https": policy.network.proxy}
    if policy.network.ca_bundle:
        session.verify = policy.network.ca_bundle
