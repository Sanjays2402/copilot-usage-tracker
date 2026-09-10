"""SQLite storage for collected Copilot usage snapshots.

Keeps a local time series of daily per-user rows and per-scope/per-team
rollups so enterprises can trend spend, acceptance rates, and seat
utilization without re-querying GitHub's API (download links expire and
daily reports only cover recent days). Schema is intentionally simple;
swap for Postgres/DuckDB/BigQuery at scale.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS user_daily (
    day TEXT NOT NULL,
    scope TEXT NOT NULL,
    user_id INTEGER NOT NULL,
    user_login TEXT,
    ai_credits_used REAL DEFAULT 0,
    interactions INTEGER DEFAULT 0,
    loc_added INTEGER DEFAULT 0,
    raw_json TEXT,
    PRIMARY KEY (day, scope, user_id)
);
CREATE TABLE IF NOT EXISTS scope_daily (
    day TEXT NOT NULL,
    scope TEXT NOT NULL,
    scope_type TEXT NOT NULL,
    ai_credits_used REAL DEFAULT 0,
    billed_usd REAL DEFAULT 0,
    active_users INTEGER DEFAULT 0,
    PRIMARY KEY (day, scope)
);
CREATE TABLE IF NOT EXISTS team_daily (
    day TEXT NOT NULL,
    scope TEXT NOT NULL,
    team_id INTEGER NOT NULL,
    slug TEXT,
    ai_credits_used REAL DEFAULT 0,
    active_users INTEGER DEFAULT 0,
    PRIMARY KEY (day, scope, team_id)
);
"""


class UsageStore:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.conn = sqlite3.connect(self.path)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(SCHEMA)

    def upsert_user_day(self, day: str, scope: str, user_id: int, **metrics) -> None:
        raw = metrics.pop("raw", None)
        self.conn.execute(
            """INSERT INTO user_daily
               (day, scope, user_id, user_login, ai_credits_used, interactions,
                loc_added, raw_json)
               VALUES (?,?,?,?,?,?,?,?)
               ON CONFLICT(day, scope, user_id) DO UPDATE SET
                 user_login=excluded.user_login,
                 ai_credits_used=excluded.ai_credits_used,
                 interactions=excluded.interactions,
                 loc_added=excluded.loc_added,
                 raw_json=excluded.raw_json""",
            (
                day,
                scope,
                user_id,
                metrics.get("user_login"),
                metrics.get("ai_credits_used", 0) or 0,
                metrics.get("interactions", 0) or 0,
                metrics.get("loc_added", 0) or 0,
                json.dumps(raw) if raw is not None else None,
            ),
        )
        self.conn.commit()

    def upsert_scope_day(self, day: str, scope: str, scope_type: str, **metrics) -> None:
        self.conn.execute(
            """INSERT INTO scope_daily
               (day, scope, scope_type, ai_credits_used, billed_usd, active_users)
               VALUES (?,?,?,?,?,?)
               ON CONFLICT(day, scope) DO UPDATE SET
                 scope_type=excluded.scope_type,
                 ai_credits_used=excluded.ai_credits_used,
                 billed_usd=excluded.billed_usd,
                 active_users=excluded.active_users""",
            (
                day,
                scope,
                scope_type,
                metrics.get("ai_credits_used", 0) or 0,
                metrics.get("billed_usd", 0) or 0,
                metrics.get("active_users", 0) or 0,
            ),
        )
        self.conn.commit()

    def upsert_team_day(self, day: str, scope: str, team_id: int, **metrics) -> None:
        self.conn.execute(
            """INSERT INTO team_daily
               (day, scope, team_id, slug, ai_credits_used, active_users)
               VALUES (?,?,?,?,?,?)
               ON CONFLICT(day, scope, team_id) DO UPDATE SET
                 slug=excluded.slug,
                 ai_credits_used=excluded.ai_credits_used,
                 active_users=excluded.active_users""",
            (
                day,
                scope,
                team_id,
                metrics.get("slug"),
                metrics.get("ai_credits_used", 0) or 0,
                metrics.get("active_users", 0) or 0,
            ),
        )
        self.conn.commit()

    def monthly_credits(self, year_month: str, scope: str | None = None) -> float:
        q = "SELECT COALESCE(SUM(ai_credits_used),0) AS s FROM scope_daily WHERE day LIKE ?"
        args: list = [f"{year_month}%"]
        if scope:
            q += " AND scope = ?"
            args.append(scope)
        return self.conn.execute(q, args).fetchone()["s"]

    def top_users(self, year_month: str, limit: int = 10) -> list[dict]:
        rows = self.conn.execute(
            """SELECT user_login, SUM(ai_credits_used) AS credits
               FROM user_daily WHERE day LIKE ?
               GROUP BY user_login ORDER BY credits DESC LIMIT ?""",
            (f"{year_month}%", limit),
        ).fetchall()
        return [dict(r) for r in rows]

    def close(self) -> None:
        self.conn.close()
