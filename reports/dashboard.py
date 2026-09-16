"""CLI-only dashboard: funnel metrics, ranked lead table, and CSV export."""
from __future__ import annotations

import csv
from typing import Any

from storage.db import get_dashboard_detail_rows, get_funnel_metrics

FUNNEL_LABELS = [
    ("businesses_found", "Businesses Found"),
    ("analyzed", "Analyzed"),
    ("qualified", "Qualified"),
    ("proposals_generated", "Proposals Generated"),
    ("outreach_drafted", "Outreach Drafted"),
    ("outreach_approved", "Outreach Approved"),
    ("outreach_sent", "Outreach Sent"),
    ("responses_logged", "Responses Logged"),
    ("interested", "Interested (Warm+Converted)"),
    ("clients_won", "Clients Won"),
]


def print_funnel() -> None:
    metrics = get_funnel_metrics()
    width = max(len(label) for _, label in FUNNEL_LABELS)
    print(f"\n{'Outreach Funnel':^{width + 12}}\n")
    print("-" * (width + 12))
    for key, label in FUNNEL_LABELS:
        value = metrics.get(key, 0)
        print(f"{label:<{width + 2}}{value:>10,}")


def print_ranked_leads(limit: int = 50) -> None:
    rows = get_dashboard_detail_rows(limit)
    if not rows:
        print("\nNo leads in database.")
        return

    header = (
        f"{'Business':<26} {'Category':<14} {'Rank':<6} {'Qual':<6} {'Proposal':<16} "
        f"{'Pipeline':<18} {'Budget':<16}"
    )
    print("\n" + header)
    print("-" * len(header))
    for row in rows:
        name = _truncate(row["name"] or "?", 24)
        rank = row["rank_score"] if row["rank_score"] is not None else "-"
        qual = row["total_score"] if row["total_score"] is not None else "-"
        proposal = _truncate(row["package_name"] or row["proposal_status"] or "Not started", 14)
        pipeline = _truncate(row["pipeline_status"] or "New", 16)
        budget = _format_budget(row)
        print(
            f"{name:<26} {_truncate(row['category'] or '', 12):<14} {str(rank):<6} "
            f"{str(qual):<6} {proposal:<16} {pipeline:<18} {budget:<16}"
        )


def print_dashboard(limit: int = 50) -> None:
    print_funnel()
    print_ranked_leads(limit)


def export_dashboard_csv(path: str, limit: int = 50) -> None:
    metrics = get_funnel_metrics()
    rows = get_dashboard_detail_rows(limit)

    with open(path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["Section", "Metric", "Value"])
        for key, label in FUNNEL_LABELS:
            w.writerow(["funnel", label, metrics.get(key, 0)])
        w.writerow([])
        w.writerow(["Business", "Category", "Rank Score", "Qualification", "Priority", "Proposal Status",
                     "Budget Min", "Budget Max", "Weeks Min", "Weeks Max", "Package Name",
                     "Pipeline Status", "Interest Level", "Last Contact Date"])
        for row in rows:
            w.writerow([
                row["name"], row["category"], row["rank_score"], row["total_score"],
                row["qual_priority"], row["proposal_status"], row["cost_min"], row["cost_max"],
                row["weeks_min"], row["weeks_max"], row["package_name"],
                row["pipeline_status"], row["interest_level"], row["last_contact_date"],
            ])
    print(f"Dashboard exported to {path}")


def _truncate(value: str, max_len: int) -> str:
    value = str(value)
    return value if len(value) <= max_len else value[: max_len - 1] + "…"


def _format_budget(row: Any) -> str:
    cmin = row["cost_min"] if "cost_min" in row.keys() else None
    cmax = row["cost_max"] if "cost_max" in row.keys() else None
    if cmin is None or cmax is None:
        return "-"
    return f"${cmin}–${cmax}"
