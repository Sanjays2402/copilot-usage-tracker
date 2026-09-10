"""GitHub token handling: resolved efficiently, never persisted by the tool.

Resolution order (first hit wins; the result is cached in memory for the
process lifetime, so the token is looked up once no matter how many API
calls the run makes):

1. ``GITHUB_TOKEN`` env var -- CI / containers / secrets managers.
2. System keyring -- the OS credential store (Windows Credential Manager,
   macOS Keychain, Linux Secret Service). Written only by
   ``copilot-usage login`` with explicit user consent; removed by `logout`.
3. ``gh`` CLI session (``gh auth token``) -- reuses an existing login, so
   no new secret is created at all.
4. Interactive prompt (``getpass``) -- typed in, held in memory only.

What "never stored anywhere" means concretely:

- The tool never writes the token to a file: not to ``policy.yaml``, not
  to the SQLite DB, not to the audit log, not to any cache.
- The token field is excluded from ``repr(Settings)`` so it can't leak
  into tracebacks or logs.
- The audit logger records only method/host/path/safe params -- the
  ``Authorization`` header and signed download-URL tokens never touch disk.
- Displayed only masked (``ghp_…abcd``); full value only ever exists in
  process memory, passed straight to the ``Authorization`` header.
"""

from __future__ import annotations

import getpass
import os
import shutil
import subprocess

import requests

SERVICE_NAME = "copilot-usage-tracker"
KEYRING_ACCOUNT = "github-token"

_cached_token: str | None = None
_cached_source: str | None = None


class TokenNotFoundError(RuntimeError):
    """Raised when no token source yields a token (with guidance)."""

    def __init__(self) -> None:
        super().__init__(
            "No GitHub token found. Authenticate with one of:\n"
            "  copilot-usage login          # guided login (OS keyring optional)\n"
            "  export GITHUB_TOKEN=...      # env var (CI / containers)\n"
            "  gh auth login               # reuse the GitHub CLI session"
        )


def _from_env() -> str | None:
    return os.environ.get("GITHUB_TOKEN") or None


def _from_keyring() -> str | None:
    try:
        import keyring

        return keyring.get_password(SERVICE_NAME, KEYRING_ACCOUNT)
    except Exception:  # noqa: BLE001 - no usable backend: fall through
        return None


def _from_gh_cli() -> str | None:
    if not shutil.which("gh"):
        return None
    try:
        proc = subprocess.run(
            ["gh", "auth", "token"],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        return proc.stdout.strip() or None
    except Exception:  # noqa: BLE001 - gh missing/broken: fall through
        return None


def reset_cache() -> None:
    """Forget the cached token (used by tests and `logout`)."""
    global _cached_token, _cached_source
    _cached_token, _cached_source = None, None


def resolve_token() -> tuple[str, str]:
    """Return ``(token, source)`` where source is env|keyring|gh.

    Non-interactive: never prompts. Raises TokenNotFoundError when nothing
    yields a token.
    """
    global _cached_token, _cached_source
    if _cached_token is not None:
        return _cached_token, _cached_source or "cached"
    for source, provider in (
        ("env", _from_env),
        ("keyring", _from_keyring),
        ("gh", _from_gh_cli),
    ):
        token = provider()
        if token:
            _cached_token, _cached_source = token, source
            return token, source
    raise TokenNotFoundError()


def prompt_token() -> str:
    """Ask for a token interactively; input is hidden and memory-only."""
    return getpass.getpass(
        "GitHub token (input hidden; stored nowhere by this tool): "
    ).strip()


def mask_token(token: str) -> str:
    """Render a token safe for display, e.g. ``ghp_…abcd``."""
    if len(token) <= 8:
        return "****"
    return f"{token[:4]}…{token[-4:]}"


def save_to_keyring(token: str) -> None:
    """Store the token in the OS keyring (explicit user consent only)."""
    import keyring

    keyring.set_password(SERVICE_NAME, KEYRING_ACCOUNT, token)
    # populate the process cache so the login session just works
    global _cached_token, _cached_source
    _cached_token, _cached_source = token, "keyring"


def delete_from_keyring() -> bool:
    """Remove the token from the OS keyring; returns True if one existed."""
    try:
        import keyring

        if keyring.get_password(SERVICE_NAME, KEYRING_ACCOUNT) is None:
            return False
        keyring.delete_password(SERVICE_NAME, KEYRING_ACCOUNT)
        return True
    except Exception:  # noqa: BLE001 - no usable backend
        return False
    finally:
        reset_cache()


def validate_token(token: str, api_base: str = "https://api.github.com"
                   ) -> tuple[str, str]:
    """Check a token against GET /user; returns (login, scopes)."""
    resp = requests.get(
        f"{api_base}/user",
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
        },
        timeout=15,
    )
    resp.raise_for_status()
    return resp.json().get("login", "?"), resp.headers.get("X-OAuth-Scopes", "")
