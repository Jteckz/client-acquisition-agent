"""SQLite storage for discovered businesses and generated lead reports."""
from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path

from config.settings import settings

SCHEMA = """
CREATE TABLE IF NOT EXISTS businesses (
    place_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    category TEXT,
    website TEXT,
    phone TEXT,
    address TEXT,
    latitude REAL,
    longitude REAL,
    rating REAL,
    rating_count INTEGER,
    discovered_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS lead_reports (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    place_id TEXT NOT NULL REFERENCES businesses(place_id),
    problems_json TEXT,
    solutions_json TEXT,
    potential_value TEXT,
    lead_score INTEGER,
    priority TEXT,
    score_reasons_json TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_lead_reports_score ON lead_reports(lead_score DESC);
"""


def init_db() -> None:
    Path(settings.DATABASE_PATH).parent.mkdir(parents=True, exist_ok=True)
    with get_connection() as conn:
        conn.executescript(SCHEMA)


@contextmanager
def get_connection():
    conn = sqlite3.connect(settings.DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def save_business(business) -> None:
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO businesses
                (place_id, name, category, website, phone, address, latitude, longitude, rating, rating_count)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(place_id) DO UPDATE SET
                name=excluded.name, category=excluded.category, website=excluded.website,
                phone=excluded.phone, address=excluded.address, latitude=excluded.latitude,
                longitude=excluded.longitude, rating=excluded.rating, rating_count=excluded.rating_count
            """,
            (
                business.place_id, business.name, business.category, business.website,
                business.phone, business.address, business.latitude, business.longitude,
                business.rating, business.rating_count,
            ),
        )


def save_lead_report(report) -> int:
    with get_connection() as conn:
        cur = conn.execute(
            """
            INSERT INTO lead_reports
                (place_id, problems_json, solutions_json, potential_value, lead_score, priority, score_reasons_json)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                report.business.place_id,
                json.dumps(report.problems),
                json.dumps(report.solutions),
                report.potential_value,
                report.lead_score,
                report.priority,
                json.dumps(report.score_reasons),
            ),
        )
        return cur.lastrowid


def get_top_leads(limit: int = 20) -> list[sqlite3.Row]:
    with get_connection() as conn:
        cur = conn.execute(
            """
            SELECT b.name, b.category, b.website, b.phone, b.address,
                   r.lead_score, r.priority, r.problems_json, r.solutions_json, r.potential_value
            FROM lead_reports r
            JOIN businesses b ON b.place_id = r.place_id
            ORDER BY r.lead_score DESC
            LIMIT ?
            """,
            (limit,),
        )
        return cur.fetchall()
