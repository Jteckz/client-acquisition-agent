"""
CLI entry point for the client acquisition agent.

Business discovery runs on OpenStreetMap — no API key needed. Pass either
a free-text --query, or explicit --category/--location (more reliable,
skips text parsing).

Examples:
    python main.py --category restaurant --location "Dar es Salaam" --limit 10
    python main.py --query "hair salons in Kariakoo" --limit 5 --show-top 5
    python main.py --list-categories
"""
from __future__ import annotations

import argparse

from discovery.osm_places import list_supported_categories
from pipeline import run_pipeline
from storage.db import get_top_leads, init_db


def main() -> None:
    parser = argparse.ArgumentParser(description="AI-powered client acquisition agent (V1)")
    parser.add_argument("--query", help='Free text, e.g. "restaurants in Dar es Salaam"')
    parser.add_argument("--category", help="Explicit category, e.g. restaurant")
    parser.add_argument("--location", help='Explicit location, e.g. "Dar es Salaam"')
    parser.add_argument("--limit", type=int, default=10, help="Max businesses to process")
    parser.add_argument(
        "--show-top", type=int, default=0,
        help="After running, print the top N leads across ALL runs stored in the DB",
    )
    parser.add_argument(
        "--list-categories", action="store_true",
        help="Print supported --category values and exit",
    )
    args = parser.parse_args()

    if args.list_categories:
        print("Supported categories:")
        for c in list_supported_categories():
            print(f"  - {c}")
        return

    if not args.query and not (args.category and args.location):
        parser.error("Provide --query, or both --category and --location.")

    reports, _, map_path = run_pipeline(
        query=args.query, category=args.category, location=args.location, max_results=args.limit
    )

    print(f"\nGenerated {len(reports)} lead reports.\n")
    for report_text in reports:
        print(report_text)
        print("=" * 60)

    if map_path:
        print(f"\nMap saved to {map_path} — open it in a browser to see leads plotted.")

    if args.show_top:
        init_db()
        print(f"\nTop {args.show_top} leads overall:\n")
        for row in get_top_leads(args.show_top):
            print(f"{row['lead_score']:>3}/100  [{row['priority']:<6}]  {row['name']} ({row['category']})")


if __name__ == "__main__":
    main()
