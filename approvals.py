from __future__ import annotations

"""Persistent store for Slack approval status."""

import json
import sqlite3
import time
from pathlib import Path
from typing import Dict, Optional

SCHEMA = """
CREATE TABLE IF NOT EXISTS approvals (
    run_id TEXT NOT NULL,
    item_id TEXT NOT NULL,
    title TEXT NOT NULL,
    body TEXT NOT NULL,
    status TEXT NOT NULL,
    slack_ts TEXT,
    channel TEXT,
    approver_id TEXT,
    approver_name TEXT,
    reason TEXT,
    updated_at REAL NOT NULL,
    PRIMARY KEY (run_id, item_id)
)
"""


class ApprovalStore:
    def __init__(self, db_path: Path | str):
        raw_path = Path(db_path)
        self.path = raw_path.expanduser()
        parent = self.path.parent if self.path.parent != Path("") else Path(".")
        parent.mkdir(parents=True, exist_ok=True)
        self._ensure_schema()

    def _connect(self) -> sqlite3.Connection:
        try:
            return sqlite3.connect(self.path, timeout=5, check_same_thread=False)
        except sqlite3.OperationalError as exc:
            raise sqlite3.OperationalError(f"{exc} (path={self.path})") from exc

    def _ensure_schema(self) -> None:
        with self._connect() as conn:
            conn.execute(SCHEMA)

    def upsert_item(
        self,
        *,
        run_id: str,
        item_id: str,
        title: str,
        body: str,
        status: str = "pending",
        slack_ts: str | None = None,
        channel: str | None = None,
    ) -> None:
        now = time.time()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO approvals (run_id, item_id, title, body, status, slack_ts, channel, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(run_id, item_id)
                DO UPDATE SET
                    title=excluded.title,
                    body=excluded.body,
                    status=excluded.status,
                    slack_ts=COALESCE(excluded.slack_ts, approvals.slack_ts),
                    channel=COALESCE(excluded.channel, approvals.channel),
                    updated_at=?
                """,
                (run_id, item_id, title, body, status, slack_ts, channel, now, now),
            )

    def attach_slack_refs(self, *, run_id: str, item_id: str, slack_ts: str, channel: str) -> None:
        with self._connect() as conn:
            conn.execute(
                "UPDATE approvals SET slack_ts=?, channel=? WHERE run_id=? AND item_id=?",
                (slack_ts, channel, run_id, item_id),
            )

    def update_status(
        self,
        *,
        run_id: str,
        item_id: str,
        status: str,
        approver_id: str | None = None,
        approver_name: str | None = None,
        reason: str | None = None,
    ) -> None:
        if status not in {"approved", "rejected", "pending"}:
            raise ValueError(f"Unknown status {status}")
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE approvals
                SET status=?, approver_id=?, approver_name=?, reason=?, updated_at=?
                WHERE run_id=? AND item_id=?
                """,
                (status, approver_id, approver_name, reason, time.time(), run_id, item_id),
            )

    def get_item(self, *, run_id: str, item_id: str) -> Optional[Dict[str, str]]:
        with self._connect() as conn:
            cursor = conn.execute(
                "SELECT run_id, item_id, title, body, status, slack_ts, channel, approver_id, approver_name, reason, updated_at FROM approvals WHERE run_id=? AND item_id=?",
                (run_id, item_id),
            )
            row = cursor.fetchone()
        if not row:
            return None
        keys = [
            "run_id",
            "item_id",
            "title",
            "body",
            "status",
            "slack_ts",
            "channel",
            "approver_id",
            "approver_name",
            "reason",
            "updated_at",
        ]
        return dict(zip(keys, row))

    def wait_for_status(
        self,
        *,
        run_id: str,
        item_id: str,
        timeout: int,
        poll_interval: float = 5.0,
    ) -> Dict[str, str | None]:
        deadline = time.time() + timeout
        while time.time() < deadline:
            record = self.get_item(run_id=run_id, item_id=item_id)
            if record and record.get("status") in {"approved", "rejected"}:
                return record
            time.sleep(poll_interval)
        return {
            "run_id": run_id,
            "item_id": item_id,
            "status": "timeout",
        }

__all__ = ["ApprovalStore"]
