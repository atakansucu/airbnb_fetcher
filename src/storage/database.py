"""SQLite persistence for seen listings and notification deduplication."""

from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, Iterator

from src.models import Listing


class ListingStore:
    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.db_path, timeout=30)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def _init_schema(self) -> None:
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS listings (
                    listing_id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    url TEXT NOT NULL,
                    total_price_eur REAL,
                    review_score REAL,
                    distance_km REAL,
                    neighborhood TEXT,
                    composite_score REAL,
                    is_entire_home INTEGER DEFAULT 0,
                    free_cancellation INTEGER DEFAULT 0,
                    is_superhost INTEGER DEFAULT 0,
                    raw_json TEXT,
                    first_seen_at TEXT NOT NULL,
                    last_seen_at TEXT NOT NULL,
                    notified_at TEXT,
                    notification_count INTEGER DEFAULT 0
                );

                CREATE TABLE IF NOT EXISTS price_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    listing_id TEXT NOT NULL,
                    total_price_eur REAL,
                    recorded_at TEXT NOT NULL,
                    FOREIGN KEY (listing_id) REFERENCES listings(listing_id)
                );

                CREATE TABLE IF NOT EXISTS notifications (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    listing_id TEXT NOT NULL,
                    alert_type TEXT NOT NULL,
                    message_hash TEXT NOT NULL,
                    sent_at TEXT NOT NULL,
                    UNIQUE(listing_id, alert_type, message_hash)
                );

                CREATE INDEX IF NOT EXISTS idx_listings_last_seen
                    ON listings(last_seen_at);
                CREATE INDEX IF NOT EXISTS idx_price_history_listing
                    ON price_history(listing_id, recorded_at);
                """
            )

    def get_listing(self, listing_id: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM listings WHERE listing_id = ?", (listing_id,)
            ).fetchone()
            return dict(row) if row else None

    def upsert_listing(
        self,
        listing: Listing,
        composite_score: float | None = None,
    ) -> tuple[bool, bool]:
        """
        Insert or update listing.
        Returns (is_new, price_dropped).
        """
        now = datetime.utcnow().isoformat()
        existing = self.get_listing(listing.listing_id)
        is_new = existing is None
        price_dropped = False

        old_price = existing["total_price_eur"] if existing else None
        new_price = listing.total_price_eur

        if (
            not is_new
            and old_price is not None
            and new_price is not None
            and new_price < old_price - 0.5
        ):
            price_dropped = True

        with self._connect() as conn:
            if is_new:
                conn.execute(
                    """
                    INSERT INTO listings (
                        listing_id, title, url, total_price_eur, review_score,
                        distance_km, neighborhood, composite_score,
                        is_entire_home, free_cancellation, is_superhost,
                        raw_json, first_seen_at, last_seen_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        listing.listing_id,
                        listing.title,
                        listing.url,
                        listing.total_price_eur,
                        listing.review_score,
                        listing.distance_km,
                        listing.neighborhood,
                        composite_score,
                        int(listing.is_entire_home),
                        int(listing.free_cancellation),
                        int(listing.is_superhost),
                        json.dumps(listing.raw, default=str),
                        now,
                        now,
                    ),
                )
            else:
                conn.execute(
                    """
                    UPDATE listings SET
                        title = ?, url = ?, total_price_eur = ?,
                        review_score = ?, distance_km = ?, neighborhood = ?,
                        composite_score = COALESCE(?, composite_score),
                        is_entire_home = ?, free_cancellation = ?, is_superhost = ?,
                        raw_json = ?, last_seen_at = ?
                    WHERE listing_id = ?
                    """,
                    (
                        listing.title,
                        listing.url,
                        listing.total_price_eur,
                        listing.review_score,
                        listing.distance_km,
                        listing.neighborhood,
                        composite_score,
                        int(listing.is_entire_home),
                        int(listing.free_cancellation),
                        int(listing.is_superhost),
                        json.dumps(listing.raw, default=str),
                        now,
                        listing.listing_id,
                    ),
                )

            if new_price is not None:
                conn.execute(
                    """
                    INSERT INTO price_history (listing_id, total_price_eur, recorded_at)
                    VALUES (?, ?, ?)
                    """,
                    (listing.listing_id, new_price, now),
                )

        return is_new, price_dropped

    def was_notified(self, listing_id: str, alert_type: str, message_hash: str) -> bool:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT 1 FROM notifications
                WHERE listing_id = ? AND alert_type = ? AND message_hash = ?
                """,
                (listing_id, alert_type, message_hash),
            ).fetchone()
            return row is not None

    def mark_notified(self, listing_id: str, alert_type: str, message_hash: str) -> None:
        now = datetime.utcnow().isoformat()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT OR IGNORE INTO notifications
                (listing_id, alert_type, message_hash, sent_at)
                VALUES (?, ?, ?, ?)
                """,
                (listing_id, alert_type, message_hash, now),
            )
            conn.execute(
                """
                UPDATE listings SET notified_at = ?,
                notification_count = notification_count + 1
                WHERE listing_id = ?
                """,
                (now, listing_id),
            )

    def count_listings(self) -> int:
        with self._connect() as conn:
            row = conn.execute("SELECT COUNT(*) AS c FROM listings").fetchone()
            return int(row["c"]) if row else 0

    def get_top_listing_by_score(
        self,
        max_total_price_eur: float,
        max_distance_km: float | None = None,
    ) -> Listing | None:
        with self._connect() as conn:
            if max_distance_km is not None:
                row = conn.execute(
                    """
                    SELECT * FROM listings
                    WHERE composite_score IS NOT NULL
                      AND total_price_eur IS NOT NULL
                      AND total_price_eur <= ?
                      AND distance_km IS NOT NULL
                      AND distance_km <= ?
                    ORDER BY composite_score DESC
                    LIMIT 1
                    """,
                    (max_total_price_eur, max_distance_km),
                ).fetchone()
            else:
                row = conn.execute(
                    """
                    SELECT * FROM listings
                    WHERE composite_score IS NOT NULL
                      AND total_price_eur IS NOT NULL
                      AND total_price_eur <= ?
                    ORDER BY composite_score DESC
                    LIMIT 1
                    """,
                    (max_total_price_eur,),
                ).fetchone()
        if not row:
            return None
        return self._listing_from_row(dict(row))

    @staticmethod
    def _listing_from_row(row: dict[str, Any]) -> Listing:
        raw: dict[str, Any] = {}
        if row.get("raw_json"):
            try:
                raw = json.loads(row["raw_json"])
            except json.JSONDecodeError:
                raw = {}
        return Listing(
            listing_id=row["listing_id"],
            title=row["title"],
            url=row["url"],
            total_price_eur=row.get("total_price_eur"),
            review_score=row.get("review_score"),
            distance_km=row.get("distance_km"),
            neighborhood=row.get("neighborhood"),
            is_entire_home=bool(row.get("is_entire_home")),
            free_cancellation=bool(row.get("free_cancellation")),
            is_superhost=bool(row.get("is_superhost")),
            lat=raw.get("lat"),
            lng=raw.get("lng"),
            room_type=raw.get("room_type"),
            review_count=raw.get("review_count"),
            self_check_in=bool(raw.get("self_check_in")),
            raw=raw,
        )
