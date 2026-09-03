from __future__ import annotations

import hashlib
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from .config import Vehicle
from .models import CheckResult, OutstandingItem

UTC = timezone.utc


def iso(dt: datetime | None) -> str | None:
    return dt.astimezone(UTC).isoformat() if dt else None


class Store:
    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(path)
        self.conn.row_factory = sqlite3.Row
        self._migrate()

    def close(self) -> None:
        self.conn.close()

    def _migrate(self) -> None:
        self.conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS checks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                plate_number TEXT NOT NULL,
                province TEXT NOT NULL,
                checked_at TEXT NOT NULL,
                status TEXT NOT NULL,
                detail TEXT NOT NULL DEFAULT ''
            );
            CREATE TABLE IF NOT EXISTS transactions (
                id TEXT PRIMARY KEY,
                plate_number TEXT NOT NULL,
                province TEXT NOT NULL,
                transaction_date TEXT,
                amount REAL,
                status TEXT NOT NULL,
                first_seen TEXT NOT NULL,
                last_seen TEXT NOT NULL,
                deadline TEXT,
                source_url TEXT NOT NULL,
                raw_excerpt TEXT NOT NULL DEFAULT '',
                last_notified_at TEXT,
                notification_level TEXT
            );
            CREATE INDEX IF NOT EXISTS idx_transactions_vehicle_status
            ON transactions(plate_number, province, status);
            CREATE TABLE IF NOT EXISTS alerts (
                key TEXT PRIMARY KEY,
                last_sent_at TEXT NOT NULL
            );
            """
        )
        self.conn.commit()

    def record_check(self, vehicle: Vehicle, result: CheckResult, now: datetime) -> None:
        self.conn.execute(
            "INSERT INTO checks (plate_number, province, checked_at, status, detail) VALUES (?, ?, ?, ?, ?)",
            (vehicle.plate_number, vehicle.province, iso(now), result.status.value, result.detail[:2000]),
        )
        self.conn.commit()

    @staticmethod
    def transaction_id(vehicle: Vehicle, item: OutstandingItem) -> str:
        date_key = iso(item.transaction_date) or "unknown-date"
        amount_key = "unknown-amount" if item.amount is None else f"{item.amount:.2f}"
        raw = f"{vehicle.plate_number}|{vehicle.province}|{date_key}|{amount_key}|{item.raw_excerpt[:120]}"
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]

    def upsert_transaction(self, vehicle: Vehicle, item: OutstandingItem, now: datetime, deadline: datetime | None) -> sqlite3.Row:
        tx_id = self.transaction_id(vehicle, item)
        existing = self.conn.execute("SELECT * FROM transactions WHERE id = ?", (tx_id,)).fetchone()
        if existing:
            self.conn.execute(
                "UPDATE transactions SET last_seen = ?, status = 'UNPAID', source_url = ?, raw_excerpt = ? WHERE id = ?",
                (iso(now), item.source_url, item.raw_excerpt[:1000], tx_id),
            )
        else:
            self.conn.execute(
                """INSERT INTO transactions (
                    id, plate_number, province, transaction_date, amount, status,
                    first_seen, last_seen, deadline, source_url, raw_excerpt
                ) VALUES (?, ?, ?, ?, ?, 'UNPAID', ?, ?, ?, ?, ?)""",
                (tx_id, vehicle.plate_number, vehicle.province, iso(item.transaction_date), item.amount,
                 iso(now), iso(now), iso(deadline), item.source_url, item.raw_excerpt[:1000]),
            )
        self.conn.commit()
        return self.conn.execute("SELECT * FROM transactions WHERE id = ?", (tx_id,)).fetchone()

    def mark_vehicle_clear(self, vehicle: Vehicle, now: datetime) -> int:
        cursor = self.conn.execute(
            "UPDATE transactions SET status = 'PAID', last_seen = ? WHERE plate_number = ? AND province = ? AND status = 'UNPAID'",
            (iso(now), vehicle.plate_number, vehicle.province),
        )
        self.conn.commit()
        return cursor.rowcount

    def set_notified(self, tx_id: str, now: datetime, level: str) -> None:
        self.conn.execute(
            "UPDATE transactions SET last_notified_at = ?, notification_level = ? WHERE id = ?",
            (iso(now), level, tx_id),
        )
        self.conn.commit()

    def can_send_alert(self, key: str, now: datetime, cooldown_hours: int) -> bool:
        row = self.conn.execute("SELECT last_sent_at FROM alerts WHERE key = ?", (key,)).fetchone()
        if not row:
            return True
        previous = datetime.fromisoformat(row["last_sent_at"])
        return (now - previous).total_seconds() >= cooldown_hours * 3600

    def mark_alert_sent(self, key: str, now: datetime) -> None:
        self.conn.execute(
            "INSERT INTO alerts (key, last_sent_at) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET last_sent_at = excluded.last_sent_at",
            (key, iso(now)),
        )
        self.conn.commit()

    def list_transactions(self, limit: int = 200) -> list[sqlite3.Row]:
        return self.conn.execute(
            "SELECT * FROM transactions ORDER BY COALESCE(deadline, first_seen) DESC LIMIT ?", (limit,)
        ).fetchall()

    def latest_checks(self) -> list[sqlite3.Row]:
        return self.conn.execute(
            """SELECT c.* FROM checks c JOIN (
                SELECT plate_number, province, MAX(id) AS max_id
                FROM checks GROUP BY plate_number, province
            ) x ON c.id = x.max_id ORDER BY c.plate_number"""
        ).fetchall()
