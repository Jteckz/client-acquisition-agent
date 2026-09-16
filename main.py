"""
CLI entry point for the client acquisition agent (V3).

Subcommands:
    discover             V1 discovery/research/report (+ V2 proposals with --generate-proposals)
    rank                 compute/refresh opportunity rankings, print top N
    prepare-outreach     draft a personalized outreach message (Pending Approval)
    list-drafts          list outreach drafts, optionally filtered by status
    approve              approve ONE draft (human action; never automatic)
    reject               reject ONE draft
    mark-sent            record that a HUMAN sent an approved draft themselves
    log-response         classify a human-pasted reply and update the CRM
    follow-ups           list leads due for follow-up
    dashboard            print funnel metrics + ranked lead table
    export-dashboard     write funnel + detail rows to CSV
    insights             knowledge-base summary by category
    model-status         show which model(s) Ollama currently has resident in RAM

Backward-compatible: the old flat invocation (e.g. `python main.py
--category restaurant --location "Dar es Salaam" --limit 3`) is routed to
the `discover` subcommand automatically.

AI discovers → AI analyzes → AI drafts → A HUMAN approves → A HUMAN sends.
This tool NEVER sends a message of any kind.
"""
from __future__ import annotations

import argparse
import sys

from config.settings import settings
from discovery.osm_places import list_supported_categories
from pipeline import run_pipeline
from storage.db import get_top_leads, init_db

SUBCOMMANDS = {
    "discover", "rank", "prepare-outreach", "list-drafts", "approve", "reject",
    "mark-sent", "log-response", "follow-ups", "dashboard", "export-dashboard", "insights",
    "model-status",
}


def main() -> None:
    argv = sys.argv[1:]
    # Backward compatibility: old flat flags route to the discover subcommand.
    if not argv or argv[0] not in SUBCOMMANDS:
        argv = ["discover"] + argv

    parser = argparse.ArgumentParser(description="AI-powered client acquisition agent (V3)")
    sub = parser.add_subparsers(dest="command", required=True)

    # ── discover (V1 + V2) ─────────────────────────────────────────────
    p_d = sub.add_parser("discover", help="Discover businesses and run V1/V2 pipeline")
    p_d.add_argument("--query", help='Free text, e.g. "restaurants in Dar es Salaam"')
    p_d.add_argument("--category", help="Explicit category, e.g. restaurant")
    p_d.add_argument("--location", help='Explicit location, e.g. "Dar es Salaam"')
    p_d.add_argument("--limit", type=int, default=10, help="Max businesses to process")
    p_d.add_argument("--show-top", type=int, default=0,
                     help="After running, print the top N leads across ALL runs stored in the DB")
    p_d.add_argument("--list-categories", action="store_true",
                     help="Print supported --category values and exit")
    p_d.add_argument("--generate-proposals", action="store_true",
                     help="Run V2 qualification -> design -> cost -> proposal for qualified leads")
    p_d.add_argument("--min-qualification", type=int, default=None,
                     help="Override minimum qualification score for proposals")
    p_d.add_argument("--workers", type=int, default=6, help="Max parallel workers (default: 6)")
    p_d.set_defaults(func=cmd_discover)

    # ── V3 subcommands ─────────────────────────────────────────────────
    p_rank = sub.add_parser("rank", help="Compute/refresh opportunity rankings")
    p_rank.add_argument("--limit", type=int, default=20)
    p_rank.set_defaults(func=cmd_rank)

    p_prep = sub.add_parser("prepare-outreach", help="Draft a personalized outreach message")
    p_prep.add_argument("--place-id", required=True)
    p_prep.add_argument("--channel", required=True, choices=["email", "linkedin", "whatsapp"])
    p_prep.add_argument("--followup", action="store_true",
                        help="Draft a follow-up to the most recent SENT message for this lead")
    p_prep.set_defaults(func=cmd_prepare_outreach)

    p_list = sub.add_parser("list-drafts", help="List outreach drafts")
    p_list.add_argument("--status", default=None, help="Filter by status (e.g. 'Pending Approval')")
    p_list.set_defaults(func=cmd_list_drafts)

    p_approve = sub.add_parser("approve", help="Approve ONE outreach draft (human action)")
    p_approve.add_argument("--draft-id", type=int, required=True)
    p_approve.set_defaults(func=cmd_approve)

    p_reject = sub.add_parser("reject", help="Reject ONE outreach draft")
    p_reject.add_argument("--draft-id", type=int, required=True)
    p_reject.set_defaults(func=cmd_reject)

    p_sent = sub.add_parser("mark-sent", help="Record that a HUMAN sent an approved draft")
    p_sent.add_argument("--draft-id", type=int, required=True)
    p_sent.set_defaults(func=cmd_mark_sent)

    p_log = sub.add_parser("log-response", help="Log + classify a human-pasted reply")
    p_log.add_argument("--draft-id", type=int, required=True)
    p_log.add_argument("--text", required=True)
    p_log.set_defaults(func=cmd_log_response)

    p_fu = sub.add_parser("follow-ups", help="List leads due for follow-up")
    p_fu.set_defaults(func=cmd_followups)

    p_dash = sub.add_parser("dashboard", help="Print funnel + ranked leads")
    p_dash.add_argument("--limit", type=int, default=50)
    p_dash.set_defaults(func=cmd_dashboard)

    p_exp = sub.add_parser("export-dashboard", help="Export funnel + detail rows to CSV")
    p_exp.add_argument("--path", required=True)
    p_exp.add_argument("--limit", type=int, default=50)
    p_exp.set_defaults(func=cmd_export)

    p_ins = sub.add_parser("insights", help="Knowledge-base summary by category")
    p_ins.set_defaults(func=cmd_insights)

    p_ms = sub.add_parser("model-status",
                          help="Show which model(s) Ollama currently has loaded in memory")
    p_ms.set_defaults(func=cmd_model_status)

    args = parser.parse_args(argv)
    try:
        args.func(args)
    except ValueError as exc:
        raise SystemExit(f"Error: {exc}")


# ── Command handlers ───────────────────────────────────────────────────

def cmd_discover(args: argparse.Namespace) -> None:
    if args.list_categories:
        print("Supported categories:")
        for c in list_supported_categories():
            print(f"  - {c}")
        return

    if not args.query and not (args.category and args.location):
        raise SystemExit("discover: provide --query, or both --category and --location.")

    if args.min_qualification is not None:
        settings.MIN_QUALIFICATION_SCORE_FOR_PROPOSAL = args.min_qualification

    reports, _, map_path, proposals = run_pipeline(
        query=args.query,
        category=args.category,
        location=args.location,
        max_results=args.limit,
        generate_proposals=args.generate_proposals,
        max_workers=getattr(args, "workers", 6),
    )

    print(f"\nGenerated {len(reports)} lead reports.\n")
    for report_text in reports:
        print(report_text)
        print("=" * 60)

    if map_path:
        print(f"\nMap saved to {map_path} — open it in a browser to see leads plotted.")

    if args.generate_proposals:
        print(f"\nGenerated {len(proposals)} proposals.\n")
        for p in proposals:
            budget = f"${p.cost_estimate.estimated_cost_min}–${p.cost_estimate.estimated_cost_max}"
            timeline = f"{p.cost_estimate.estimated_weeks_min}–{p.cost_estimate.estimated_weeks_max}w"
            print(f"  {p.business_name:<30} {p.proposed_solution.package_name:<30} {budget:<16} {timeline:<10} {p.status}")
        print()

    if args.show_top:
        init_db()
        print(f"\nTop {args.show_top} leads overall:\n")
        for row in get_top_leads(args.show_top):
            print(f"{row['lead_score']:>3}/100  [{row['priority']:<6}]  {row['name']} ({row['category']})")


def cmd_rank(args: argparse.Namespace) -> None:
    init_db()
    from analysis.opportunity_ranker import rank_all
    rankings = rank_all(args.limit)
    if not rankings:
        print("No leads to rank yet — run `discover` first.")
        return
    print(f"\nTop {len(rankings)} opportunities:\n")
    for name, category, r in rankings:
        print(
            f"{r.final_score:>3}/100  {name:<28} ({category:<12})  "
            f"need={r.need_score:<3} budget={r.budget_score:<3} reach={r.reachability_score}"
        )


def cmd_prepare_outreach(args: argparse.Namespace) -> None:
    init_db()
    from analysis.followup_agent import draft_followup
    from analysis.outreach_drafter import draft_outreach
    from analysis.outreach_preparer import prepare_hook
    from analysis.problem_detector import ProblemAnalysis
    from discovery.models import Business
    from pipeline import research_business
    from storage.db import get_business, get_latest_problems, save_outreach_draft

    if args.followup:
        draft = draft_followup(args.place_id, args.channel)
    else:
        row = get_business(args.place_id)
        if row is None:
            raise SystemExit(f"Unknown business: {args.place_id}")
        business = Business(
            place_id=row["place_id"], name=row["name"], category=row["category"] or "",
            website=row["website"], phone=row["phone"], address=row["address"],
            latitude=row["latitude"], longitude=row["longitude"],
        )
        bundle = research_business(business)
        problems = ProblemAnalysis(problems=get_latest_problems(args.place_id))
        hook = prepare_hook(business.name, business.category, problems, bundle)
        draft = draft_outreach(args.place_id, args.channel, business.name, hook)

    draft_id = save_outreach_draft(draft)
    print(f"\nDraft #{draft_id} — {args.channel} — status: {draft.status}\n")
    if draft.subject:
        print(f"Subject: {draft.subject}\n")
    print(draft.body)
    print(f"\nPersonalization hook: {draft.personalization_hook}")
    print("\nThis draft is NOT sent. Review it, then run: python main.py approve --draft-id "
          f"{draft_id} (or reject). A human approves and sends every message.")


def cmd_list_drafts(args: argparse.Namespace) -> None:
    init_db()
    from storage.db import get_outreach_drafts
    drafts = get_outreach_drafts(args.status)
    if not drafts:
        print("No drafts found.")
        return
    print(f"\n{'ID':<5} {'Business':<24} {'Channel':<10} {'Status':<18} Created")
    print("-" * 70)
    for d in drafts:
        print(f"{d['id']:<5} {d['name'][:22]:<24} {d['channel']:<10} {d['status']:<18} {d['created_at']}")


def cmd_approve(args: argparse.Namespace) -> None:
    init_db()
    from storage.db import approve_draft
    d = approve_draft(args.draft_id)
    print(f"Draft {args.draft_id} APPROVED. A human can now send it and run `mark-sent --draft-id {args.draft_id}`.")


def cmd_reject(args: argparse.Namespace) -> None:
    init_db()
    from storage.db import reject_draft
    reject_draft(args.draft_id)
    print(f"Draft {args.draft_id} REJECTED.")


def cmd_mark_sent(args: argparse.Namespace) -> None:
    init_db()
    from storage.db import mark_draft_sent
    d = mark_draft_sent(args.draft_id)
    print(
        f"Draft {args.draft_id} marked SENT ({d['sent_at']}) for {d['place_id']}. "
        f"CRM updated to 'Contacted'. The system did not send anything — you did."
    )


def cmd_log_response(args: argparse.Namespace) -> None:
    init_db()
    from analysis.response_classifier import classify_response
    from storage.db import get_outreach_draft, save_response, update_crm_after_response

    draft = get_outreach_draft(args.draft_id)
    if draft is None:
        raise SystemExit(f"Unknown draft: {args.draft_id}")
    if draft["status"] not in ("Approved", "Sent"):
        raise SystemExit(f"Draft {args.draft_id} is '{draft['status']}' — only log responses for approved/sent outreach.")

    status = classify_response(args.text)
    save_response(draft["place_id"], args.draft_id, args.text, status)
    update_crm_after_response(draft["place_id"], status)
    print(f"Response for {draft['place_id']} classified as: {status}")
    print("CRM updated accordingly.")


def cmd_followups(args: argparse.Namespace) -> None:
    init_db()
    from analysis.followup_agent import list_leads_due_for_followup
    leads = list_leads_due_for_followup()
    if not leads:
        print("No leads due for follow-up.")
        return
    print("\nLeads due for follow-up:\n")
    print(f"{'Place ID':<24} {'Business':<28} {'Last Contact':<16} {'Next Follow-up'}")
    print("-" * 78)
    for l in leads:
        print(f"{l['place_id']:<24} {l['name'][:26]:<28} {l['last_contact_date']:<16} {l['next_follow_up_date'] or '-'}")
    print("\nTo draft a follow-up: python main.py prepare-outreach --place-id <id> --channel <channel> --followup")


def cmd_dashboard(args: argparse.Namespace) -> None:
    init_db()
    from reports.dashboard import print_dashboard
    print_dashboard(args.limit)


def cmd_export(args: argparse.Namespace) -> None:
    init_db()
    from reports.dashboard import export_dashboard_csv
    export_dashboard_csv(args.path, args.limit)


def cmd_insights(args: argparse.Namespace) -> None:
    init_db()
    from analysis.insights import print_insights
    print_insights()


def cmd_model_status(args: argparse.Namespace) -> None:
    """Print the models currently resident in Ollama (GET /api/ps).

    Lets the operator sanity-check RAM usage during a real run against
    `ollama ps` directly.
    """
    import requests

    host = settings.OLLAMA_HOST.rstrip("/")
    try:
        resp = requests.get(f"{host}/api/ps", timeout=15)
        resp.raise_for_status()
        models = (resp.json() or {}).get("models", [])
    except requests.RequestException as exc:
        raise SystemExit(f"Could not reach Ollama at {host}: {exc}")

    if not models:
        print("No models currently resident in memory (Ollama loaded nothing).")
        return

    print(f"{'Model':<32} {'Size':>12} {'VRAM':>12}  Expires at")
    print("-" * 90)
    for m in models:
        name = m.get("name") or m.get("model") or "?"
        size = m.get("size", 0)
        vram = m.get("size_vram", 0)
        print(
            f"{name:<32} {_human_bytes(size):>12} {_human_bytes(vram):>12}  {m.get('expires_at') or '-'}"
        )


def _human_bytes(n: int) -> str:
    if not n:
        return "-"
    value = float(n)
    for unit in ("B", "KB", "MB", "GB"):
        if value < 1024 or unit == "GB":
            return f"{value:.1f}{unit}" if unit == "GB" else f"{value:.0f}{unit}"
        value /= 1024
    return f"{value:.1f}GB"


if __name__ == "__main__":
    main()
