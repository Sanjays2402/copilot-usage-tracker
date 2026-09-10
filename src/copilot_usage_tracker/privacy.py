"""User pseudonymization for privacy-sensitive enterprises.

When ``privacy.anonymize_users`` is on, logins and numeric user ids are
replaced with stable, salted HMAC pseudonyms (``user_9f2ac41d07be``) before
anything is written to the store. Aggregation still works; re-identification
requires the salt from policy.yaml / COPILOT_USER_SALT.
"""

from __future__ import annotations

import hashlib
import hmac


def pseudonym(value: str, salt: str) -> str:
    """Stable salted pseudonym for a login, e.g. ``user_9f2ac41d07be``."""
    digest = hmac.new(
        salt.encode(), value.strip().lower().encode(), hashlib.sha256
    ).hexdigest()[:12]
    return f"user_{digest}"


def pseudonym_id(user_id: int, salt: str) -> int:
    """Stable salted pseudonym for a numeric user id (fits in 31 bits)."""
    digest = hmac.new(
        salt.encode(), str(user_id).encode(), hashlib.sha256
    ).hexdigest()[:8]
    return int(digest, 16) % (2**31)
