"""SQLite storage for collected Copilot usage snapshots.

Keeps a local time series of daily per-user rows, per-scope/per-team
rollups, and per-model token rows (from the AI usage report export) so
enterprises can trend spend, acceptance rates, and seat utilization without
re-querying GitHub's API (download links expire and daily reports only
cover recent days). Schema is intentionally simple; swap for
Postgres/DuckDB/BigQuery at scale.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timedelta, timezone
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
CREATE TABLE IF NOT EXISTS model_daily (
    day TEXT NOT NULL,
    scope TEXT NOT NULL,
    model TEXT NOT NULL,
    user_login TEXT NOT NULL DEFAULT '',
    input_tokens INTEGER DEFAULT 0,
    output_tokens INTEGER DEFAULT 0,
    cache_read_tokens INTEGER DEFAULT 0,
    cache_write_tokens INTEGER DEFAULT 0,
    gross_amount_usd REAL DEFAULT 0,
    net_amount_usd REAL DEFAULT 0,
    PRIMARY KEY (day, scope, model, user_login)
);
"""


class UsageStore:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.conn = sqlite3.connect(self.path)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(SCHEMA)

    # -- writes ----------------------------------------------------------
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

    def upsert_model_day(self, day: str, scope: str, model: str, **metrics) -> None:
        self.conn.execute(
            """INSERT INTO model_daily
               (day, scope, model, user_login, input_tokens, output_tokens,
                cache_read_tokens, cache_write_tokens,
                gross_amount_usd, net_amount_usd)
               VALUES (?,?,?,?,?,?,?,?,?,?)
               ON CONFLICT(day, scope, model, user_login) DO UPDATE SET
                 input_tokens=excluded.input_tokens,
                 output_tokens=excluded.output_tokens,
                 cache_read_tokens=excluded.cache_read_tokens,
                 cache_write_tokens=excluded.cache_write_tokens,
                 gross_amount_usd=excluded.gross_amount_usd,
                 net_amount_usd=excluded.net_amount_usd""",
            (
                day,
                scope,
                model,
                metrics.get("user_login", "") or "",
                metrics.get("input_tokens", 0) or 0,
                metrics.get("output_tokens", 0) or 0,
                metrics.get("cache_read_tokens", 0) or 0,
                metrics.get("cache_write_tokens", 0) or 0,
                metrics.get("gross_amount_usd", 0) or 0,
                metrics.get("net_amount_usd", 0) or 0,
            ),
        )
        self.conn.commit()

    # -- reads -----------------------------------------------------------
    def _scoped(self, table: str, month: str, scope: str | None, extra: str = ""):
        q = f"FROM {table} WHERE day LIKE ?"
        args: list = [f"{month}%"]
        if scope:
            q += " AND scope = ?"
            args.append(scope)
        return q + extra, args

    def monthly_credits(self, year_month: str, scope: str | None = None) -> float:
        q, args = self._scoped("scope_daily", year_month, scope)
        return self.conn.execute(
            f"SELECT COALESCE(SUM(ai_credits_used),0) AS s {q}", args
        ).fetchone()["s"]

    def monthly_active_users(self, year_month: str, scope: str | None = None) -> int:
        q, args = self._scoped("user_daily", year_month, scope)
        return self.conn.execute(
            f"SELECT COUNT(DISTINCT user_id) AS n {q}", args
        ).fetchone()["n"]

    def daily_series(self, year_month: str, scope: str | None = None) -> list[dict]:
        q, args = self._scoped("scope_daily", year_month, scope)
        rows = self.conn.execute(
            f"SELECT day, SUM(ai_credits_used) AS ai_credits_used {q} "
            "GROUP BY day ORDER BY day",
            args,
        ).fetchall()
        return [dict(r) for r in rows]

    def team_totals(self, year_month: str, scope: str | None = None) -> list[dict]:
        q, args = self._scoped("team_daily", year_month, scope)
        rows = self.conn.execute(
            "SELECT slug, SUM(ai_credits_used) AS ai_credits_used, "
            f"MAX(active_users) AS active_users {q} "
            "GROUP BY slug ORDER BY ai_credits_used DESC",
            args,
        ).fetchall()
        return [dict(r) for r in rows]

    def top_users(self, year_month: str, limit: int = 10,
                  scope: str | None = None) -> list[dict]:
        q, args = self._scoped("user_daily", year_month, scope)
        rows = self.conn.execute(
            "SELECT user_login, SUM(ai_credits_used) AS credits "
            f"{q} GROUP BY user_login ORDER BY credits DESC LIMIT ?",
            args + [limit],
        ).fetchall()
        return [dict(r) for r in rows]

    def model_token_totals(
        self, year_month: str, scope: str | None = None
    ) -> dict:
        q, args = self._scoped("model_daily", year_month, scope)
        r = self.conn.execute(
            "SELECT COALESCE(SUM(input_tokens),0) AS i, "
            "COALESCE(SUM(output_tokens),0) AS o, "
            "COALESCE(SUM(cache_read_tokens),0) AS cr, "
            f"COALESCE(SUM(cache_write_tokens),0) AS cw {q}",
            args,
        ).fetchone()
        return {
            "input_tokens": r["i"],
            "output_tokens": r["o"],
            "cache_read_tokens": r["cr"],
            "cache_write_tokens": r["cw"],
        }

    def model_breakdown(
        self, year_month: str, scope: str | None = None
    ) -> list[dict]:
        q, args = self._scoped("model_daily", year_month, scope)
        rows = self.conn.execute(
            "SELECT model, SUM(input_tokens) AS input_tokens, "
            "SUM(output_tokens) AS output_tokens, "
            "SUM(cache_read_tokens) AS cache_read_tokens, "
            "SUM(cache_write_tokens) AS cache_write_tokens, "
            "SUM(gross_amount_usd) AS gross_amount_usd, "
            f"SUM(net_amount_usd) AS net_amount_usd {q} "
            "GROUP BY model ORDER BY gross_amount_usd DESC",
            args,
        ).fetchall()
        return [dict(r) for r in rows]

    def purge_older_than(self, days: int) -> dict:
        """Delete rows older than `days` (cutoff in UTC); returns per-table counts."""
        cutoff = (
            datetime.now(timezone.utc).date() - timedelta(days=days)
        ).isoformat()
        counts = {}
        for table in ("user_daily", "scope_daily", "team_daily", "model_daily"):
            cur = self.conn.execute(
                f"DELETE FROM {table} WHERE day < ?", (cutoff,)
            )
            counts[table] = cur.rowcount
        self.conn.commit()
        return counts

    def close(self) -> None:
        self.conn.close()
