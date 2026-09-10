"""Trust & transparency helpers: prove the app is safe, in-app.

Enterprises rightly ask "what does this do with our token and our data?".
These pure functions power the dashboard's Security tab:

- :func:`token_privilege_verdict` -- judges whether a GitHub token carries
  more power than the app needs (read-only).
- :func:`data_inventory` -- exactly what is stored locally, with row counts.
- :func:`network_summary` -- proof from the audit log that the app only
  ever issues read-only requests to GitHub's API.
"""

from __future__ import annotations

from urllib.parse import urlparse

# Scopes that grant write/admin power -- the app never needs any of these.
# Kept as a denylist (not an allowlist) because fine-grained PATs advertise
# no scopes at all via X-OAuth-Scopes, and GHES deployments vary.
WRITE_SCOPES = {
    "repo",
    "write:org",
    "admin:org",
    "write:enterprise",
    "admin:enterprise",
    "delete_repo",
    "workflow",
    "write:packages",
    "delete:packages",
    "admin:repo_hook",
    "write:repo_hook",
    "user",  # full user write (emails, keys, ...)
    "admin:public_key",
    "write:public_key",
    "admin:gpg_key",
    "write:gpg_key",
    "codespace",
}


def token_privilege_verdict(scopes: str | None) -> dict:
    """Judge a token's privilege from its advertised OAuth scopes.

    Returns ``level`` (``"least-privilege"``, ``"elevated"``, or
    ``"unknown"``), the offending ``write_scopes``, and a human ``message``.
    ``None``/empty scopes (fine-grained PATs) can carry any permission, so
    they are reported as unknown rather than blessed.
    """
    if not scopes:
        return {
            "level": "unknown",
            "write_scopes": [],
            "message": (
                "GitHub did not advertise this token's scopes "
                "(typical for fine-grained tokens). Use a token with only "
                "read access to Copilot business metrics."
            ),
        }
    advertised = {s.strip() for s in scopes.replace(",", " ").split() if s.strip()}
    if not advertised:
        return {
            "level": "unknown",
            "write_scopes": [],
            "message": (
                "GitHub did not advertise this token's scopes "
                "(typical for fine-grained tokens). Use a token with only "
                "read access to Copilot business metrics."
            ),
        }
    bad = sorted(advertised & WRITE_SCOPES)
    if bad:
        return {
            "level": "elevated",
            "write_scopes": bad,
            "message": (
                "This token has write/admin scopes the app never uses "
                f"({', '.join(bad)}). Consider a read-only token: the app "
                "only issues GET requests."
            ),
        }
    return {
        "level": "least-privilege",
        "write_scopes": [],
        "message": (
            "No write/admin scopes detected. This token follows the least-privilege principle."
        ),
    }


TABLE_DESCRIPTIONS = {
    "user_daily": "Per-user, per-day credit usage and engagement",
    "scope_daily": "Daily org/enterprise rollups",
    "team_daily": "Daily per-team rollups",
    "model_daily": "Per-model token usage and billed dollars",
}


def data_inventory(store) -> list[dict]:
    """Row counts per local table, so users see exactly what is stored."""
    rows = []
    for table, description in TABLE_DESCRIPTIONS.items():
        try:
            count = store.conn.execute(f"SELECT COUNT(*) AS n FROM {table}").fetchone()["n"]
        except Exception:  # noqa: BLE001 - a missing table is not fatal
            count = 0
        rows.append({"table": table, "rows": count, "contents": description})
    return rows


def network_summary(records: list[dict], api_base: str) -> dict:
    """Summarize outbound API traffic from audit-log records.

    Proves the read-only story: every request the app makes is a GET to
    the configured GitHub API host, and nothing is ever sent anywhere else.
    """
    api_host = urlparse(api_base).netloc.lower()
    methods: dict[str, int] = {}
    other_hosts: set[str] = set()
    non_get = 0
    for r in records:
        method = str(r.get("method", "")).upper()
        methods[method] = methods.get(method, 0) + 1
        if method != "GET":
            non_get += 1
        host = str(r.get("host", "")).lower()
        if host and host != api_host:
            other_hosts.add(host)
    return {
        "total_requests": len(records),
        "methods": methods,
        "non_get_requests": non_get,
        "third_party_hosts": sorted(other_hosts),
        "read_only": non_get == 0,
        "local_only": not other_hosts,
    }
