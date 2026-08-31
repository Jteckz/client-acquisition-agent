"""SQLite storage for discovered businesses and generated lead reports."""
from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import date, timedelta
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

CREATE TABLE IF NOT EXISTS qualification_scores (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    place_id TEXT NOT NULL REFERENCES businesses(place_id),
    business_activity_score INTEGER,
    digital_presence_score INTEGER,
    ability_to_pay_score INTEGER,
    solution_need_score INTEGER,
    total_score INTEGER,
    priority TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS proposals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    place_id TEXT NOT NULL REFERENCES businesses(place_id),
    package_name TEXT,
    features_json TEXT,
    tech_stack_json TEXT,
    cost_min INTEGER,
    cost_max INTEGER,
    weeks_min INTEGER,
    weeks_max INTEGER,
    status TEXT DEFAULT 'Draft',
    pdf_path TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS reachability_info (
    place_id TEXT PRIMARY KEY REFERENCES businesses(place_id),
    email_found TEXT,
    contactable_channels_json TEXT,
    reachability_score INTEGER,
    checked_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS crm_leads (
    place_id TEXT PRIMARY KEY REFERENCES businesses(place_id),
    pipeline_status TEXT DEFAULT 'New',
    interest_level TEXT DEFAULT 'Unknown',
    last_contact_date TEXT,
    next_follow_up_date TEXT,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS outreach_drafts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    place_id TEXT NOT NULL REFERENCES businesses(place_id),
    channel TEXT NOT NULL,
    subject TEXT,
    personalization_hook TEXT,
    body TEXT,
    status TEXT DEFAULT 'Pending Approval',
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    approved_at TEXT,
    sent_at TEXT
);

CREATE TABLE IF NOT EXISTS responses (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    place_id TEXT NOT NULL REFERENCES businesses(place_id),
    outreach_draft_id INTEGER NOT NULL REFERENCES outreach_drafts(id),
    response_text TEXT NOT NULL,
    classified_status TEXT,
    analyzed_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS opportunity_rankings (
    place_id TEXT PRIMARY KEY REFERENCES businesses(place_id),
    need_score INTEGER,
    budget_score INTEGER,
    reachability_score INTEGER,
    final_score INTEGER,
    ranked_at TEXT DEFAULT CURRENT_TIMESTAMP
);
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


def get_latest_qualification_score(place_id: str) -> int | None:
    """Latest stored qualification total_score for a lead, or None.

    Used by the follow-up escalation check — reads the score the pipeline
    already computed and stored during discovery.
    """
    with get_connection() as conn:
        cur = conn.execute(
            "SELECT total_score FROM qualification_scores WHERE place_id = ? ORDER BY id DESC LIMIT 1",
            (place_id,),
        )
        row = cur.fetchone()
        return row["total_score"] if row is not None else None


def save_qualification_score(place_id: str, qs) -> int:
    with get_connection() as conn:
        cur = conn.execute(
            """
            INSERT INTO qualification_scores
                (place_id, business_activity_score, digital_presence_score,
                 ability_to_pay_score, solution_need_score, total_score, priority)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                place_id,
                qs.business_activity_score,
                qs.digital_presence_score,
                qs.ability_to_pay_score,
                qs.solution_need_score,
                qs.total_score,
                qs.priority,
            ),
        )
        return cur.lastrowid


def save_proposal(place_id: str, proposal) -> int:
    with get_connection() as conn:
        cur = conn.execute(
            """
            INSERT INTO proposals
                (place_id, package_name, features_json, tech_stack_json,
                 cost_min, cost_max, weeks_min, weeks_max, status, pdf_path)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                place_id,
                proposal.proposed_solution.package_name,
                json.dumps(proposal.proposed_solution.features),
                json.dumps(proposal.tech_stack.model_dump()),
                proposal.cost_estimate.estimated_cost_min,
                proposal.cost_estimate.estimated_cost_max,
                proposal.cost_estimate.estimated_weeks_min,
                proposal.cost_estimate.estimated_weeks_max,
                proposal.status,
                proposal.pdf_path,
            ),
        )
        return cur.lastrowid


def get_dashboard_rows(limit: int = 20) -> list[sqlite3.Row]:
    with get_connection() as conn:
        cur = conn.execute(
            """
            SELECT b.name, b.category, q.total_score, q.priority as qual_priority,
                   p.status as proposal_status, p.cost_min, p.cost_max,
                   p.weeks_min, p.weeks_max, p.package_name
            FROM businesses b
            LEFT JOIN qualification_scores q ON q.place_id = b.place_id
            LEFT JOIN proposals p ON p.place_id = b.place_id
            ORDER BY q.total_score DESC
            LIMIT ?
            """,
            (limit,),
        )
        return cur.fetchall()


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


# ── V3: reachability ───────────────────────────────────────────────────

def save_reachability(place_id: str, reach) -> None:
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO reachability_info (place_id, email_found, contactable_channels_json, reachability_score)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(place_id) DO UPDATE SET
                email_found=excluded.email_found,
                contactable_channels_json=excluded.contactable_channels_json,
                reachability_score=excluded.reachability_score,
                checked_at=CURRENT_TIMESTAMP
            """,
            (place_id, reach.email_found, json.dumps(reach.contactable_channels), reach.reachability_score),
        )


def get_reachability(place_id: str) -> sqlite3.Row | None:
    with get_connection() as conn:
        cur = conn.execute(
            "SELECT email_found, contactable_channels_json, reachability_score FROM reachability_info WHERE place_id = ?",
            (place_id,),
        )
        return cur.fetchone()


# ── V3: CRM ────────────────────────────────────────────────────────────

def save_crm_lead(place_id: str, pipeline_status: str = "New", interest_level: str = "Unknown",
                  last_contact_date: str | None = None, next_follow_up_date: str | None = None) -> None:
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO crm_leads (place_id, pipeline_status, interest_level, last_contact_date, next_follow_up_date)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(place_id) DO UPDATE SET
                pipeline_status=CASE WHEN excluded.pipeline_status != 'New' THEN excluded.pipeline_status ELSE crm_leads.pipeline_status END,
                interest_level=excluded.interest_level,
                last_contact_date=COALESCE(excluded.last_contact_date, crm_leads.last_contact_date),
                next_follow_up_date=COALESCE(excluded.next_follow_up_date, crm_leads.next_follow_up_date),
                updated_at=CURRENT_TIMESTAMP
            """,
            (place_id, pipeline_status, interest_level, last_contact_date, next_follow_up_date),
        )


def get_crm_lead(place_id: str) -> sqlite3.Row | None:
    with get_connection() as conn:
        cur = conn.execute(
            "SELECT * FROM crm_leads WHERE place_id = ?",
            (place_id,),
        )
        return cur.fetchone()


def update_crm_after_response(place_id: str, classified_status: str) -> None:
    mapping = {
        "Warm Lead": ("Warm", "High"),
        "Future Opportunity": ("Future Opportunity", "Medium"),
        "Not Interested": ("Not Interested", "Low"),
        "Needs More Info": ("Warm", "Medium"),
        "Converted": ("Won", "High"),
    }
    status, interest = mapping.get(classified_status, ("Contacted", "Unknown"))
    save_crm_lead(place_id, pipeline_status=status, interest_level=interest)


# ── V3: outreach drafts ────────────────────────────────────────────────

def save_outreach_draft(draft) -> int:
    with get_connection() as conn:
        cur = conn.execute(
            """
            INSERT INTO outreach_drafts (place_id, channel, subject, personalization_hook, body, status)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (draft.place_id, draft.channel, draft.subject, draft.personalization_hook, draft.body, draft.status),
        )
        return cur.lastrowid


def get_outreach_draft(draft_id: int) -> sqlite3.Row | None:
    with get_connection() as conn:
        cur = conn.execute(
            "SELECT * FROM outreach_drafts WHERE id = ?",
            (draft_id,),
        )
        return cur.fetchone()


def get_outreach_drafts(status: str | None = None, limit: int = 50) -> list[sqlite3.Row]:
    query = """
        SELECT d.id, b.name, d.place_id, d.channel, d.subject, d.personalization_hook, d.body,
               d.status, d.created_at, d.approved_at, d.sent_at
        FROM outreach_drafts d
        JOIN businesses b ON b.place_id = d.place_id
    """
    params: tuple = ()
    if status:
        query += " WHERE d.status = ?"
        params = (status,)
    query += " ORDER BY d.id DESC LIMIT ?"
    with get_connection() as conn:
        cur = conn.execute(query, params + (limit,))
        return cur.fetchall()


def approve_draft(draft_id: int) -> sqlite3.Row:
    with get_connection() as conn:
        row = conn.execute("SELECT status FROM outreach_drafts WHERE id = ?", (draft_id,)).fetchone()
        if row is None:
            raise ValueError(f"Draft {draft_id} not found.")
        if row["status"] != "Pending Approval":
            raise ValueError(f"Draft {draft_id} has status '{row['status']}' — can only approve 'Pending Approval' drafts.")
        conn.execute(
            "UPDATE outreach_drafts SET status='Approved', approved_at=CURRENT_TIMESTAMP WHERE id=?",
            (draft_id,),
        )
        cur = conn.execute("SELECT * FROM outreach_drafts WHERE id = ?", (draft_id,))
        return cur.fetchone()


def reject_draft(draft_id: int) -> sqlite3.Row:
    with get_connection() as conn:
        row = conn.execute("SELECT status FROM outreach_drafts WHERE id = ?", (draft_id,)).fetchone()
        if row is None:
            raise ValueError(f"Draft {draft_id} not found.")
        if row["status"] != "Pending Approval":
            raise ValueError(f"Draft {draft_id} has status '{row['status']}' — can only reject 'Pending Approval' drafts.")
        conn.execute(
            "UPDATE outreach_drafts SET status='Rejected' WHERE id=?",
            (draft_id,),
        )
        cur = conn.execute("SELECT * FROM outreach_drafts WHERE id = ?", (draft_id,))
        return cur.fetchone()


def mark_draft_sent(draft_id: int) -> sqlite3.Row:
    """Records that a HUMAN sent this outreach themselves. Never sends anything."""
    with get_connection() as conn:
        row = conn.execute("SELECT status, place_id FROM outreach_drafts WHERE id = ?", (draft_id,)).fetchone()
        if row is None:
            raise ValueError(f"Draft {draft_id} not found.")
        if row["status"] != "Approved":
            raise ValueError(f"Draft {draft_id} has status '{row['status']}' — must be 'Approved' before sending.")
        conn.execute(
            "UPDATE outreach_drafts SET status='Sent', sent_at=CURRENT_TIMESTAMP WHERE id=?",
            (draft_id,),
        )
        today = date.today().isoformat()
        next_followup = (date.today() + timedelta(days=settings.FOLLOWUP_AFTER_DAYS)).isoformat()
        conn.execute(
            """
            INSERT INTO crm_leads (place_id, pipeline_status, interest_level, last_contact_date, next_follow_up_date)
            VALUES (?, 'Contacted', 'Unknown', ?, ?)
            ON CONFLICT(place_id) DO UPDATE SET
                pipeline_status='Contacted',
                last_contact_date=COALESCE(crm_leads.last_contact_date, ?),
                next_follow_up_date=?,
                updated_at=CURRENT_TIMESTAMP
            """,
            (row["place_id"], today, next_followup, today, next_followup),
        )
        cur = conn.execute("SELECT * FROM outreach_drafts WHERE id = ?", (draft_id,))
        return cur.fetchone()


# ── V3: responses ──────────────────────────────────────────────────────

def save_response(place_id: str, draft_id: int, response_text: str, classified_status: str) -> int:
    with get_connection() as conn:
        cur = conn.execute(
            """
            INSERT INTO responses (place_id, outreach_draft_id, response_text, classified_status)
            VALUES (?, ?, ?, ?)
            """,
            (place_id, draft_id, response_text, classified_status),
        )
        return cur.lastrowid


def get_responses(place_id: str) -> list[sqlite3.Row]:
    with get_connection() as conn:
        cur = conn.execute(
            "SELECT * FROM responses WHERE place_id = ? ORDER BY analyzed_at DESC",
            (place_id,),
        )
        return cur.fetchall()


# ── V3: opportunity rankings ───────────────────────────────────────────

def save_opportunity_ranking(place_id: str, ranking) -> None:
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO opportunity_rankings (place_id, need_score, budget_score, reachability_score, final_score)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(place_id) DO UPDATE SET
                need_score=excluded.need_score,
                budget_score=excluded.budget_score,
                reachability_score=excluded.reachability_score,
                final_score=excluded.final_score,
                ranked_at=CURRENT_TIMESTAMP
            """,
            (place_id, ranking.need_score, ranking.budget_score, ranking.reachability_score, ranking.final_score),
        )


def get_opportunity_rankings(limit: int = 20) -> list[sqlite3.Row]:
    with get_connection() as conn:
        cur = conn.execute(
            """
            SELECT b.name, b.category, r.need_score, r.budget_score, r.reachability_score, r.final_score
            FROM opportunity_rankings r
            JOIN businesses b ON b.place_id = r.place_id
            ORDER BY r.final_score DESC
            LIMIT ?
            """,
            (limit,),
        )
        return cur.fetchall()


def get_rankable_rows() -> list[sqlite3.Row]:
    """Latest qualification sub-scores per business, for the ranking engine."""
    with get_connection() as conn:
        cur = conn.execute(
            """
            SELECT b.place_id, b.name, b.category,
                   q.solution_need_score, q.ability_to_pay_score
            FROM qualification_scores q
            JOIN businesses b ON b.place_id = q.place_id
            WHERE q.id = (SELECT MAX(id) FROM qualification_scores q2 WHERE q2.place_id = q.place_id)
            """
        )
        return cur.fetchall()


# ── V3: follow-ups ─────────────────────────────────────────────────────

def get_leads_due_for_followup(days: int | None = None) -> list[sqlite3.Row]:
    days = days if days is not None else settings.FOLLOWUP_AFTER_DAYS
    cutoff = (date.today() - timedelta(days=days)).isoformat()
    with get_connection() as conn:
        cur = conn.execute(
            """
            SELECT c.place_id, b.name, b.category, c.last_contact_date, c.next_follow_up_date
            FROM crm_leads c
            JOIN businesses b ON b.place_id = c.place_id
            WHERE c.pipeline_status = 'Contacted'
              AND c.last_contact_date IS NOT NULL
              AND c.last_contact_date <= ?
              AND NOT EXISTS (
                  SELECT 1 FROM responses r
                  JOIN outreach_drafts d ON d.id = r.outreach_draft_id
                  WHERE d.place_id = c.place_id AND r.analyzed_at >= c.last_contact_date
              )
            ORDER BY c.last_contact_date ASC
            """,
            (cutoff,),
        )
        return cur.fetchall()


def get_latest_sent_draft(place_id: str, channel: str) -> sqlite3.Row | None:
    with get_connection() as conn:
        cur = conn.execute(
            """
            SELECT * FROM outreach_drafts
            WHERE place_id = ? AND channel = ? AND status = 'Sent'
            ORDER BY id DESC LIMIT 1
            """,
            (place_id, channel),
        )
        return cur.fetchone()


# ── V3: dashboard / funnel ─────────────────────────────────────────────

def get_funnel_metrics() -> dict:
    with get_connection() as conn:
        row = conn.execute(
            """
            SELECT
              (SELECT COUNT(*) FROM businesses) AS businesses_found,
              (SELECT COUNT(DISTINCT place_id) FROM lead_reports) AS analyzed,
              (SELECT COUNT(DISTINCT place_id) FROM qualification_scores) AS qualified,
              (SELECT COUNT(DISTINCT place_id) FROM proposals) AS proposals_generated,
              (SELECT COUNT(*) FROM outreach_drafts) AS outreach_drafted,
              (SELECT COUNT(*) FROM outreach_drafts WHERE status IN ('Approved','Sent')) AS outreach_approved,
              (SELECT COUNT(*) FROM outreach_drafts WHERE status='Sent') AS outreach_sent,
              (SELECT COUNT(*) FROM responses) AS responses_logged,
              (SELECT COUNT(DISTINCT place_id) FROM responses
               WHERE classified_status IN ('Warm Lead','Converted')) AS interested,
              (SELECT COUNT(*) FROM crm_leads WHERE pipeline_status='Won') AS clients_won
            """
        ).fetchone()
        return dict(row)


def get_dashboard_detail_rows(limit: int = 50) -> list[sqlite3.Row]:
    with get_connection() as conn:
        cur = conn.execute(
            """
            SELECT b.name, b.category,
                   q.total_score, q.priority AS qual_priority,
                   p.status AS proposal_status, p.cost_min, p.cost_max, p.weeks_min, p.weeks_max, p.package_name,
                   c.pipeline_status, c.interest_level, c.last_contact_date,
                   r.final_score AS rank_score
            FROM businesses b
            LEFT JOIN qualification_scores q
                ON q.place_id = b.place_id
                AND q.id = (SELECT MAX(id) FROM qualification_scores q2 WHERE q2.place_id = q.place_id)
            LEFT JOIN proposals p
                ON p.place_id = b.place_id
                AND p.id = (SELECT MAX(id) FROM proposals p2 WHERE p2.place_id = p.place_id)
            LEFT JOIN crm_leads c ON c.place_id = b.place_id
            LEFT JOIN opportunity_rankings r ON r.place_id = b.place_id
            ORDER BY r.final_score DESC NULLS LAST, b.name ASC
            LIMIT ?
            """,
            (limit,),
        )
        return cur.fetchall()


# ── V3: helpers ────────────────────────────────────────────────────────

def get_business(place_id: str) -> sqlite3.Row | None:
    with get_connection() as conn:
        cur = conn.execute("SELECT * FROM businesses WHERE place_id = ?", (place_id,))
        return cur.fetchone()


def get_latest_problems(place_id: str) -> list[str]:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT problems_json FROM lead_reports WHERE place_id = ? ORDER BY id DESC LIMIT 1",
            (place_id,),
        ).fetchone()
        if row is None:
            return []
        try:
            return json.loads(row["problems_json"] or "[]")
        except json.JSONDecodeError:
            return []
