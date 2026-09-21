"""
FastAPI backend server for the Client Acquisition Agent.

Exposes REST endpoints that the React frontend (ACA_UI) consumes.
Wraps the existing CLI functionality into HTTP endpoints.
"""
from __future__ import annotations

import json
import os
import sys
import threading
import uuid
from contextlib import asynccontextmanager
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

# Ensure project root is on sys.path
PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from config.settings import settings
from storage.db import init_db, get_connection


# ── Lifespan ──────────────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(title="Client Acquisition Agent API", version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Pydantic models ──────────────────────────────────────────────────
class DiscoverRequest(BaseModel):
    query: str | None = None
    category: str | None = None
    location: str | None = None
    limit: int = 10
    generate_proposals: bool = False
    min_qualification: int | None = None


class OutreachDraftCreate(BaseModel):
    place_id: str
    channel: str
    followup: bool = False


class ResponseLog(BaseModel):
    text: str


class SettingsUpdate(BaseModel):
    llm_provider: str | None = None
    ollama_host: str | None = None
    ollama_worker_model: str | None = None
    ollama_reasoning_model: str | None = None
    ollama_keep_alive: str | None = None
    reasoning_model_enabled: bool | None = None
    followup_escalation_score: int | None = None
    database_path: str | None = None
    min_qualification_score_for_proposal: int | None = None
    followup_after_days: int | None = None
    min_sample_size_for_insights: int | None = None


class PipelineUpdate(BaseModel):
    pipeline_status: str


class InterestUpdate(BaseModel):
    interest_level: str


class DraftStatusUpdate(BaseModel):
    status: str


# ── Discovery job state ──────────────────────────────────────────────
_jobs: dict[str, dict[str, Any]] = {}
_jobs_lock = threading.Lock()


def _run_discovery_job(job_id: str, req: DiscoverRequest):
    """Run discovery in a background thread."""
    from pipeline import run_pipeline

    def _on_progress(current: int, total: int, current_business: str, phase: str):
        with _jobs_lock:
            job = _jobs.get(job_id)
            if job is None:
                return
            job["progress"]["current"] = current
            job["progress"]["total"] = total
            job["progress"]["current_business"] = current_business
            job["progress"]["phase"] = phase

    try:
        with _jobs_lock:
            _jobs[job_id]["status"] = "running"
            _jobs[job_id]["progress"]["phase"] = "Starting discovery..."

        rendered_reports, lead_reports, map_path, proposals = run_pipeline(
            query=req.query,
            category=req.category,
            location=req.location,
            max_results=req.limit,
            generate_proposals=req.generate_proposals,
            on_progress=_on_progress,
        )

        report_data = []
        for r in lead_reports:
            report_data.append({
                "business_name": r.business.name,
                "category": r.business.category,
                "lead_score": r.lead_score,
                "priority": r.priority,
                "problems": r.problems,
                "solutions": r.solutions,
                "potential_value": r.potential_value,
            })

        with _jobs_lock:
            total = _jobs[job_id]["progress"].get("total") or len(report_data)
            # current = total processed (including per-business failures that
            # yield no report), so polling clients always observe 100% here.
            _jobs[job_id]["status"] = "completed"
            _jobs[job_id]["progress"]["phase"] = "Done"
            _jobs[job_id]["partial_results"] = report_data
            _jobs[job_id]["progress"]["current"] = total
            _jobs[job_id]["progress"]["total"] = total

    except Exception as e:
        with _jobs_lock:
            _jobs[job_id]["status"] = "failed"
            _jobs[job_id]["error"] = str(e)


# ── Helper: row to dict ──────────────────────────────────────────────
def row_to_dict(row) -> dict:
    if row is None:
        return None
    return dict(row)


def rows_to_list(rows) -> list[dict]:
    return [dict(r) for r in rows]


# ── Endpoints ────────────────────────────────────────────────────────

# -- Discovery --
@app.post("/api/discover")
async def discover(req: DiscoverRequest):
    job_id = str(uuid.uuid4())
    with _jobs_lock:
        _jobs[job_id] = {
            "job_id": job_id,
            "status": "pending",
            "progress": {"current": 0, "total": 0, "current_business": "", "phase": "Queued"},
            "partial_results": [],
        }
    thread = threading.Thread(target=_run_discovery_job, args=(job_id, req), daemon=True)
    thread.start()
    return {"job_id": job_id, "status": "pending"}


@app.get("/api/discover/{job_id}")
async def get_discovery_status(job_id: str):
    with _jobs_lock:
        job = _jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


# -- Categories --
@app.get("/api/categories")
async def list_categories():
    from discovery.osm_places import list_supported_categories
    return list_supported_categories()


# -- Businesses --
@app.get("/api/businesses/{place_id}")
async def get_business(place_id: str):
    from storage.db import get_business as db_get_business
    row = db_get_business(place_id)
    if not row:
        raise HTTPException(status_code=404, detail="Business not found")
    b = dict(row)
    # Get social_links from lead_reports if available
    with get_connection() as conn:
        lr = conn.execute(
            "SELECT score_reasons_json FROM lead_reports WHERE place_id = ? ORDER BY id DESC LIMIT 1",
            (place_id,),
        ).fetchone()
    return {
        "place_id": b["place_id"],
        "name": b["name"],
        "category": b["category"] or "",
        "website": b["website"],
        "phone": b["phone"],
        "address": b["address"],
        "latitude": b["latitude"],
        "longitude": b["longitude"],
        "rating": b.get("rating"),
        "rating_count": b.get("rating_count"),
        "social_links": [],
        "source": "openstreetmap",
        "discovered_at": b.get("discovered_at", ""),
    }


@app.get("/api/businesses/{place_id}/research")
async def get_research(place_id: str):
    from storage.db import get_reachability, get_latest_problems

    reach = get_reachability(place_id)
    problems = get_latest_problems(place_id)

    reach_dict = dict(reach) if reach else None
    channels = []
    if reach_dict and reach_dict.get("contactable_channels_json"):
        try:
            channels = json.loads(reach_dict["contactable_channels_json"])
        except json.JSONDecodeError:
            channels = []

    return {
        "website": {
            "has_website": False,
            "reachable": False,
            "is_mobile_friendly": None,
            "has_ssl": None,
            "title": None,
            "signals_found": [],
            "signals_missing": [],
            "social_links": [],
            "notes": [],
        },
        "social": {
            "platforms_found": [],
            "platforms_missing": [],
            "notes": [],
        },
        "reachability": {
            "email_found": reach_dict["email_found"] if reach_dict else None,
            "contactable_channels": channels,
            "reachability_score": reach_dict["reachability_score"] if reach_dict else 0,
        },
    }


# -- Leads --
@app.get("/api/leads")
async def list_leads(
    limit: int = Query(50, ge=1, le=200),
    priority: str | None = None,
    category: str | None = None,
    min_score: int | None = None,
    max_score: int | None = None,
):
    with get_connection() as conn:
        query = """
            SELECT b.place_id, b.name, b.category, b.website, b.phone, b.address,
                   b.latitude, b.longitude,
                   r.lead_score, r.priority, r.problems_json, r.solutions_json, r.potential_value,
                   q.total_score AS total_qualification_score,
                   c.pipeline_status,
                   b.discovered_at
            FROM lead_reports r
            JOIN businesses b ON b.place_id = r.place_id
            LEFT JOIN qualification_scores q ON q.place_id = b.place_id
                AND q.id = (SELECT MAX(id) FROM qualification_scores q2 WHERE q2.place_id = b.place_id)
            LEFT JOIN crm_leads c ON c.place_id = b.place_id
            WHERE r.id = (SELECT MAX(id) FROM lead_reports r2 WHERE r2.place_id = b.place_id)
        """
        params: list = []
        if priority:
            query += " AND r.priority = ?"
            params.append(priority)
        if category:
            query += " AND b.category = ?"
            params.append(category)
        if min_score is not None:
            query += " AND r.lead_score >= ?"
            params.append(min_score)
        if max_score is not None:
            query += " AND r.lead_score <= ?"
            params.append(max_score)
        query += " ORDER BY r.lead_score DESC LIMIT ?"
        params.append(limit)

        cur = conn.execute(query, params)
        rows = cur.fetchall()

    results = []
    for row in rows:
        d = dict(row)
        try:
            d["problems"] = json.loads(d.pop("problems_json") or "[]")
        except json.JSONDecodeError:
            d["problems"] = []
        try:
            d["solutions"] = json.loads(d.pop("solutions_json") or "[]")
        except json.JSONDecodeError:
            d["solutions"] = []
        d["potential_value"] = d.get("potential_value") or "Unknown"
        d["total_qualification_score"] = d.get("total_qualification_score") or 0
        d["pipeline_status"] = d.get("pipeline_status") or "New"
        results.append(d)
    return results


@app.get("/api/leads/{place_id}")
async def get_lead(place_id: str):
    from storage.db import get_business as db_get_business, get_latest_problems

    biz = db_get_business(place_id)
    if not biz:
        raise HTTPException(status_code=404, detail="Lead not found")

    with get_connection() as conn:
        lr = conn.execute(
            "SELECT * FROM lead_reports WHERE place_id = ? ORDER BY id DESC LIMIT 1",
            (place_id,),
        ).fetchone()
        qs = conn.execute(
            "SELECT * FROM qualification_scores WHERE place_id = ? ORDER BY id DESC LIMIT 1",
            (place_id,),
        ).fetchone()
        crm = conn.execute(
            "SELECT * FROM crm_leads WHERE place_id = ?",
            (place_id,),
        ).fetchone()
        reach = conn.execute(
            "SELECT * FROM reachability_info WHERE place_id = ?",
            (place_id,),
        ).fetchone()

    if not lr:
        raise HTTPException(status_code=404, detail="Lead report not found")

    lr_dict = dict(lr)
    problems = json.loads(lr_dict.get("problems_json") or "[]")
    solutions = json.loads(lr_dict.get("solutions_json") or "[]")
    score_reasons = json.loads(lr_dict.get("score_reasons_json") or "[]")

    qs_dict = dict(qs) if qs else {
        "business_activity_score": 0, "digital_presence_score": 0,
        "ability_to_pay_score": 0, "solution_need_score": 0,
        "total_score": 0, "priority": "Low",
    }

    reach_dict = dict(reach) if reach else {}
    channels = []
    if reach_dict.get("contactable_channels_json"):
        try:
            channels = json.loads(reach_dict["contactable_channels_json"])
        except json.JSONDecodeError:
            channels = []

    return {
        "business": {
            "place_id": biz["place_id"],
            "name": biz["name"],
            "category": biz["category"] or "",
            "website": biz["website"],
            "phone": biz["phone"],
            "address": biz["address"],
            "latitude": biz["latitude"],
            "longitude": biz["longitude"],
            "rating": biz.get("rating"),
            "rating_count": biz.get("rating_count"),
            "social_links": [],
            "source": "openstreetmap",
            "discovered_at": biz.get("discovered_at", ""),
        },
        "research": {
            "website": {
                "has_website": biz["website"] is not None,
                "reachable": biz["website"] is not None,
                "is_mobile_friendly": None,
                "has_ssl": None,
                "title": None,
                "signals_found": [],
                "signals_missing": [],
                "social_links": [],
                "notes": [],
            },
            "social": {
                "platforms_found": [],
                "platforms_missing": [],
                "notes": [],
            },
            "reachability": {
                "email_found": reach_dict.get("email_found"),
                "contactable_channels": channels,
                "reachability_score": reach_dict.get("reachability_score", 0),
            },
        },
        "problems": problems,
        "solutions": solutions,
        "potential_value": lr_dict.get("potential_value", "Unknown"),
        "lead_score": lr_dict.get("lead_score", 0),
        "priority": lr_dict.get("priority", "Low"),
        "score_reasons": score_reasons,
        "qualification": {
            "business_activity_score": qs_dict.get("business_activity_score", 0),
            "digital_presence_score": qs_dict.get("digital_presence_score", 0),
            "ability_to_pay_score": qs_dict.get("ability_to_pay_score", 0),
            "solution_need_score": qs_dict.get("solution_need_score", 0),
            "total_score": qs_dict.get("total_score", 0),
            "priority": qs_dict.get("priority", "Low"),
            "reasoning": [],
        },
    }


@app.get("/api/leads/{place_id}/qualification")
async def get_qualification(place_id: str):
    with get_connection() as conn:
        qs = conn.execute(
            "SELECT * FROM qualification_scores WHERE place_id = ? ORDER BY id DESC LIMIT 1",
            (place_id,),
        ).fetchone()
    if not qs:
        raise HTTPException(status_code=404, detail="Qualification not found")
    d = dict(qs)
    return {
        "business_activity_score": d["business_activity_score"],
        "digital_presence_score": d["digital_presence_score"],
        "ability_to_pay_score": d["ability_to_pay_score"],
        "solution_need_score": d["solution_need_score"],
        "total_score": d["total_score"],
        "priority": d["priority"],
        "reasoning": [],
    }


# -- Proposals --
@app.get("/api/proposals")
async def list_proposals(place_id: str | None = None, limit: int = 50):
    with get_connection() as conn:
        if place_id:
            cur = conn.execute(
                "SELECT p.*, b.name as business_name FROM proposals p JOIN businesses b ON b.place_id = p.place_id WHERE p.place_id = ? ORDER BY p.id DESC LIMIT ?",
                (place_id, limit),
            )
        else:
            cur = conn.execute(
                "SELECT p.*, b.name as business_name FROM proposals p JOIN businesses b ON b.place_id = p.place_id ORDER BY p.id DESC LIMIT ?",
                (limit,),
            )
        rows = cur.fetchall()

    results = []
    for row in rows:
        d = dict(row)
        try:
            d["features"] = json.loads(d.pop("features_json") or "[]")
        except json.JSONDecodeError:
            d["features"] = []
        try:
            ts = json.loads(d.pop("tech_stack_json") or "{}")
            d["tech_stack"] = ts
        except json.JSONDecodeError:
            d["tech_stack"] = {}
        results.append(d)
    return results


@app.get("/api/proposals/{proposal_id}")
async def get_proposal(proposal_id: int):
    with get_connection() as conn:
        row = conn.execute(
            "SELECT p.*, b.name as business_name FROM proposals p JOIN businesses b ON b.place_id = p.place_id WHERE p.id = ?",
            (proposal_id,),
        ).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Proposal not found")
    d = dict(row)
    try:
        d["features"] = json.loads(d.pop("features_json") or "[]")
    except json.JSONDecodeError:
        d["features"] = []
    try:
        ts = json.loads(d.pop("tech_stack_json") or "{}")
        d["tech_stack"] = ts
    except json.JSONDecodeError:
        d["tech_stack"] = {}
    return d


@app.get("/api/proposals/{proposal_id}/pdf")
async def download_proposal_pdf(proposal_id: int):
    with get_connection() as conn:
        row = conn.execute("SELECT pdf_path FROM proposals WHERE id = ?", (proposal_id,)).fetchone()
    if not row or not row["pdf_path"]:
        raise HTTPException(status_code=404, detail="PDF not found")
    pdf_path = Path(row["pdf_path"])
    if not pdf_path.is_absolute():
        pdf_path = PROJECT_ROOT / pdf_path
    if not pdf_path.exists():
        raise HTTPException(status_code=404, detail="PDF file not found on disk")
    return FileResponse(pdf_path, media_type="application/pdf", filename=pdf_path.name)


# -- Outreach drafts --
@app.get("/api/outreach/drafts")
async def list_drafts(
    status: str | None = None,
    channel: str | None = None,
    place_id: str | None = None,
    limit: int = 50,
):
    from storage.db import get_outreach_drafts
    drafts = get_outreach_drafts(status, limit)
    results = []
    for d in drafts:
        dd = dict(d)
        if channel and dd.get("channel") != channel:
            continue
        if place_id and dd.get("place_id") != place_id:
            continue
        results.append(dd)
    return results


@app.get("/api/outreach/drafts/{draft_id}")
async def get_draft(draft_id: int):
    from storage.db import get_outreach_draft
    d = get_outreach_draft(draft_id)
    if not d:
        raise HTTPException(status_code=404, detail="Draft not found")
    return dict(d)


@app.post("/api/outreach/draft")
async def create_draft(req: OutreachDraftCreate):
    from analysis.outreach_drafter import draft_outreach
    from analysis.outreach_preparer import prepare_hook
    from analysis.problem_detector import ProblemAnalysis
    from analysis.followup_agent import draft_followup
    from discovery.models import Business
    from pipeline import research_business
    from storage.db import get_business as db_get_business, get_latest_problems, save_outreach_draft

    if req.followup:
        draft = draft_followup(req.place_id, req.channel)
    else:
        row = db_get_business(req.place_id)
        if not row:
            raise HTTPException(status_code=404, detail="Business not found")
        business = Business(
            place_id=row["place_id"], name=row["name"], category=row["category"] or "",
            website=row["website"], phone=row["phone"], address=row["address"],
            latitude=row["latitude"], longitude=row["longitude"],
        )
        bundle = research_business(business)
        problems = ProblemAnalysis(problems=get_latest_problems(req.place_id))
        hook = prepare_hook(business.name, business.category, problems, bundle)
        draft = draft_outreach(req.place_id, req.channel, business.name, hook)

    draft_id = save_outreach_draft(draft)
    return {"id": draft_id, "status": draft.status, "message": "Draft created"}


@app.post("/api/outreach/drafts/{draft_id}/approve")
async def approve_draft(draft_id: int):
    from storage.db import approve_draft
    try:
        d = approve_draft(draft_id)
        return {"id": draft_id, "status": "Approved"}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/api/outreach/drafts/{draft_id}/reject")
async def reject_draft_endpoint(draft_id: int):
    from storage.db import reject_draft
    try:
        d = reject_draft(draft_id)
        return {"id": draft_id, "status": "Rejected"}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/api/outreach/drafts/{draft_id}/send")
async def mark_sent(draft_id: int):
    from storage.db import mark_draft_sent
    try:
        d = mark_draft_sent(draft_id)
        return {"id": draft_id, "status": "Sent"}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


# -- Responses --
@app.get("/api/responses")
async def list_responses(place_id: str | None = None):
    with get_connection() as conn:
        if place_id:
            cur = conn.execute(
                "SELECT * FROM responses WHERE place_id = ? ORDER BY analyzed_at DESC",
                (place_id,),
            )
        else:
            cur = conn.execute("SELECT * FROM responses ORDER BY analyzed_at DESC")
        return rows_to_list(cur.fetchall())


@app.post("/api/outreach/drafts/{draft_id}/response")
async def log_response(draft_id: int, req: ResponseLog):
    from storage.db import get_outreach_draft, save_response, update_crm_after_response
    from analysis.response_classifier import classify_response

    draft = get_outreach_draft(draft_id)
    if not draft:
        raise HTTPException(status_code=404, detail="Draft not found")
    if draft["status"] not in ("Approved", "Sent"):
        raise HTTPException(status_code=400, detail=f"Draft status is '{draft['status']}' — only log responses for approved/sent outreach.")

    status = classify_response(req.text)
    save_response(draft["place_id"], draft_id, req.text, status)
    update_crm_after_response(draft["place_id"], status)
    return {"classified_status": status, "message": "Response logged and classified"}


# -- CRM --
@app.get("/api/crm/leads")
async def list_crm_leads():
    with get_connection() as conn:
        cur = conn.execute("SELECT * FROM crm_leads")
        return rows_to_list(cur.fetchall())


@app.get("/api/crm/leads/{place_id}")
async def get_crm_lead(place_id: str):
    from storage.db import get_crm_lead
    row = get_crm_lead(place_id)
    if not row:
        return {"place_id": place_id, "pipeline_status": "New", "interest_level": "Unknown", "last_contact_date": None, "next_follow_up_date": None}
    return dict(row)


@app.put("/api/crm/leads/{place_id}/pipeline")
async def update_pipeline(place_id: str, req: PipelineUpdate):
    from storage.db import save_crm_lead
    save_crm_lead(place_id, pipeline_status=req.pipeline_status)
    return {"place_id": place_id, "pipeline_status": req.pipeline_status}


@app.put("/api/crm/leads/{place_id}/interest")
async def update_interest(place_id: str, req: InterestUpdate):
    from storage.db import save_crm_lead
    save_crm_lead(place_id, interest_level=req.interest_level)
    return {"place_id": place_id, "interest_level": req.interest_level}


# -- Follow-ups --
@app.get("/api/follow-ups")
async def list_follow_ups():
    from analysis.followup_agent import list_leads_due_for_followup
    leads = list_leads_due_for_followup()
    results = []
    for l in leads:
        d = dict(l)
        last = d.get("last_contact_date")
        if last:
            try:
                last_dt = date.fromisoformat(last)
                d["days_since_contact"] = (date.today() - last_dt).days
            except ValueError:
                d["days_since_contact"] = 0
        else:
            d["days_since_contact"] = 0
        results.append(d)
    return results


# -- Rankings --
@app.get("/api/rankings")
async def list_rankings(limit: int = 20):
    from storage.db import get_opportunity_rankings
    rows = get_opportunity_rankings(limit)
    return rows_to_list(rows)


@app.post("/api/rankings/refresh")
async def refresh_rankings():
    from analysis.opportunity_ranker import rank_all
    rankings = rank_all(50)
    return {"ranked": len(rankings), "message": "Rankings refreshed"}


# -- Dashboard --
@app.get("/api/dashboard/funnel")
async def get_funnel():
    from storage.db import get_funnel_metrics
    return get_funnel_metrics()


@app.get("/api/dashboard/leads")
async def get_dashboard_leads(limit: int = 50):
    from storage.db import get_dashboard_detail_rows
    rows = get_dashboard_detail_rows(limit)
    results = []
    for row in rows:
        d = dict(row)
        results.append(d)
    return results


@app.post("/api/dashboard/export")
async def export_dashboard(limit: int = 50):
    import csv
    import io
    from storage.db import get_funnel_metrics, get_dashboard_detail_rows

    metrics = get_funnel_metrics()
    rows = get_dashboard_detail_rows(limit)

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Metric", "Value"])
    for k, v in metrics.items():
        writer.writerow([k, v])
    writer.writerow([])
    writer.writerow(["Name", "Category", "Score", "Priority", "Proposal Status", "Cost Min", "Cost Max", "Weeks Min", "Weeks Max", "Package", "Pipeline", "Interest", "Last Contact", "Rank Score"])
    for r in rows:
        writer.writerow([
            r["name"], r["category"], r["total_score"], r["qual_priority"],
            r["proposal_status"], r["cost_min"], r["cost_max"],
            r["weeks_min"], r["weeks_max"], r["package_name"],
            r["pipeline_status"], r["interest_level"], r["last_contact_date"],
            r["rank_score"],
        ])

    from fastapi.responses import StreamingResponse
    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=dashboard_export.csv"},
    )


# -- Insights --
@app.get("/api/insights")
async def get_insights():
    from storage.db import get_connection as db_conn
    with db_conn() as conn:
        cur = conn.execute("""
            SELECT
                b.category,
                COUNT(DISTINCT b.place_id) as total,
                COUNT(DISTINCT CASE WHEN c.pipeline_status IN ('Contacted','Warm','Future Opportunity','Won') THEN b.place_id END) as contacted,
                COUNT(DISTINCT CASE WHEN r.classified_status IS NOT NULL THEN b.place_id END) as replied,
                COUNT(DISTINCT CASE WHEN c.pipeline_status = 'Won' THEN b.place_id END) as converted
            FROM businesses b
            LEFT JOIN crm_leads c ON c.place_id = b.place_id
            LEFT JOIN responses r ON r.place_id = b.place_id
            GROUP BY b.category
        """)
        rows = cur.fetchall()

    results = []
    for row in rows:
        d = dict(row)
        contacted = d["contacted"] or 0
        converted = d["converted"] or 0
        d["conversion_rate"] = round((converted / contacted * 100)) if contacted > 0 else 0

        # Get common package
        with db_conn() as conn:
            pkg = conn.execute("""
                SELECT p.package_name, COUNT(*) as cnt
                FROM proposals p
                JOIN businesses b ON b.place_id = p.place_id
                WHERE b.category = ?
                GROUP BY p.package_name
                ORDER BY cnt DESC LIMIT 1
            """, (d["category"],)).fetchone()
        d["common_package"] = dict(pkg)["package_name"] if pkg else None
        results.append(d)
    return results


# -- Settings --
@app.get("/api/settings")
async def get_settings():
    return {
        "llm_provider": settings.LLM_PROVIDER,
        "ollama_host": settings.OLLAMA_HOST,
        "ollama_worker_model": settings.OLLAMA_WORKER_MODEL,
        "ollama_reasoning_model": settings.OLLAMA_REASONING_MODEL,
        "ollama_keep_alive": settings.OLLAMA_KEEP_ALIVE,
        "reasoning_model_enabled": settings.REASONING_MODEL_ENABLED,
        "followup_escalation_score": settings.FOLLOWUP_ESCALATION_SCORE,
        "database_path": settings.DATABASE_PATH,
        "min_qualification_score_for_proposal": settings.MIN_QUALIFICATION_SCORE_FOR_PROPOSAL,
        "followup_after_days": settings.FOLLOWUP_AFTER_DAYS,
        "min_sample_size_for_insights": settings.MIN_SAMPLE_SIZE_FOR_INSIGHTS,
    }


@app.put("/api/settings")
async def update_settings(req: SettingsUpdate):
    if req.llm_provider is not None:
        settings.LLM_PROVIDER = req.llm_provider
    if req.ollama_host is not None:
        settings.OLLAMA_HOST = req.ollama_host
    if req.ollama_worker_model is not None:
        settings.OLLAMA_WORKER_MODEL = req.ollama_worker_model
    if req.ollama_reasoning_model is not None:
        settings.OLLAMA_REASONING_MODEL = req.ollama_reasoning_model
    if req.ollama_keep_alive is not None:
        settings.OLLAMA_KEEP_ALIVE = req.ollama_keep_alive
    if req.reasoning_model_enabled is not None:
        settings.REASONING_MODEL_ENABLED = req.reasoning_model_enabled
    if req.followup_escalation_score is not None:
        settings.FOLLOWUP_ESCALATION_SCORE = req.followup_escalation_score
    if req.database_path is not None:
        settings.DATABASE_PATH = req.database_path
    if req.min_qualification_score_for_proposal is not None:
        settings.MIN_QUALIFICATION_SCORE_FOR_PROPOSAL = req.min_qualification_score_for_proposal
    if req.followup_after_days is not None:
        settings.FOLLOWUP_AFTER_DAYS = req.followup_after_days
    if req.min_sample_size_for_insights is not None:
        settings.MIN_SAMPLE_SIZE_FOR_INSIGHTS = req.min_sample_size_for_insights
    return await get_settings()


# -- Model Status --
@app.get("/api/model-status")
async def get_model_status():
    import requests as req_lib
    host = settings.OLLAMA_HOST.rstrip("/")
    try:
        resp = req_lib.get(f"{host}/api/ps", timeout=15)
        resp.raise_for_status()
        models = (resp.json() or {}).get("models", [])
    except Exception:
        models = []

    results = []
    for m in models:
        results.append({
            "name": m.get("name") or m.get("model") or "?",
            "size": m.get("size", 0),
            "size_vram": m.get("size_vram", 0),
            "expires_at": m.get("expires_at"),
        })
    return results


# -- Health --
@app.get("/api/health")
async def health():
    return {"status": "ok", "version": "1.0.0"}


# ── Serve frontend static files (production) ─────────────────────────
DIST_DIR = PROJECT_ROOT / "ACA_UI" / "dist"

if (DIST_DIR / "assets").is_dir() and (DIST_DIR / "index.html").is_file():
    app.mount("/assets", StaticFiles(directory=str(DIST_DIR / "assets")), name="static-assets")

    @app.get("/{full_path:path}")
    async def serve_spa(request: Request, full_path: str):
        """Serve the SPA for all non-API routes."""
        file_path = DIST_DIR / full_path
        if file_path.is_file():
            return FileResponse(str(file_path))
        return FileResponse(str(DIST_DIR / "index.html"))


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
