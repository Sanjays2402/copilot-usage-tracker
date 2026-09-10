"""Append-only audit log of every GitHub API call the tool makes.

One JSON object per line: timestamp, method, host, path, allowlisted query
params, HTTP status. The Authorization header is never written, and only
non-sensitive query params are kept. Compliance teams can ship this file to
their SIEM to prove the tool is read-only and scoped correctly.
"""

from __future__ import annotations

import contextlib
import json
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import parse_qsl, urlparse

# Query params safe to retain; everything else is dropped from the log.
SAFE_PARAMS = {"day", "year", "month", "user", "per_page", "page", "type"}


class AuditLogger:
    def __init__(self, path: str | Path | None = None, enabled: bool = True):
        self.enabled = enabled and path is not None
        self.path = Path(path).expanduser() if path else None

    def log(
        self,
        method: str,
        url: str,
        status: int | None = None,
        note: str = "",
    ) -> None:
        if not self.enabled or self.path is None:
            return
        with contextlib.suppress(Exception):  # auditing must never break collection
            parts = urlparse(url)
            record = {
                "ts": datetime.now(timezone.utc).isoformat(),
                "method": method.upper(),
                "host": parts.netloc,
                "path": parts.path,
                "params": {
                    k: v for k, v in parse_qsl(parts.query) if k in SAFE_PARAMS
                },
                "status": status,
            }
            if note:
                record["note"] = note
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(record) + "\n")


class AuditMixin:
    """Give API clients an optional audit logger."""

    audit: AuditLogger | None = None

    def _audit(self, method: str, url: str, status: int | None = None,
               note: str = "") -> None:
        if self.audit is not None:
            self.audit.log(method, url, status, note)
