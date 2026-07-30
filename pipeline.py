"""
Orchestrates the full V1 workflow, mirroring the diagram in the project
spec:

  Business Source -> Business Data Collector -> Research Agent ->
  Business Analysis -> Problem Detection -> Solution Suggestions -> Lead Report
"""
from __future__ import annotations

import logging

from discovery.models import Business, LeadReport, ResearchBundle
from discovery.osm_places import parse_query, search_businesses
from research.reviews_analyzer import analyze_reviews
from research.social_checker import check_social_presence
from research.website_checker import check_website
from reports.map_builder import build_leads_map
from reports.report_builder import build_lead_report, render_report
from storage.db import init_db, save_business, save_lead_report

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


def research_business(business: Business) -> ResearchBundle:
    """Runs all research checks (website, reviews, social) for one business."""
    logger.info("Researching: %s", business.name)

    website_findings = check_website(business.website)
    review_findings = analyze_reviews(business.place_id)

    # Social links can come from OSM's own contact:* tags AND from links
    # scraped off the business's website — merge and dedupe both sources.
    social_links = list(dict.fromkeys(business.social_links + website_findings.social_links))
    social_findings = check_social_presence(social_links)

    return ResearchBundle(
        business=business,
        website=website_findings,
        reviews=review_findings,
        social=social_findings,
    )


def run_pipeline(
    query: str | None = None,
    category: str | None = None,
    location: str | None = None,
    max_results: int = 10,
) -> tuple[list[str], list[LeadReport], str | None]:
    """
    Full pipeline for one search. Pass either `query` (e.g. "restaurants in
    Dar es Salaam") OR explicit `category`/`location`. Returns
    (rendered_markdown_reports, LeadReport_objects, path_to_map_html).
    """
    init_db()

    if not category or not location:
        if not query:
            raise ValueError("Provide either `query` or both `category` and `location`.")
        category, location = parse_query(query)

    logger.info("Discovering '%s' businesses near '%s'", category, location)
    businesses = search_businesses(category, location, max_results=max_results)
    logger.info("Found %d businesses", len(businesses))

    rendered_reports: list[str] = []
    lead_reports: list[LeadReport] = []

    for business in businesses:
        try:
            save_business(business)
            bundle = research_business(business)
            report = build_lead_report(bundle)
            save_lead_report(report)
            rendered_reports.append(render_report(report))
            lead_reports.append(report)
            logger.info(
                "Scored %s: %d/100 (%s)", business.name, report.lead_score, report.priority
            )
        except Exception:
            logger.exception("Failed to process business: %s", business.name)
            continue

    map_path = build_leads_map(lead_reports) if lead_reports else None
    return rendered_reports, lead_reports, map_path


if __name__ == "__main__":
    # Quick manual smoke test — prefer `python main.py` for real usage.
    reports, _, map_path = run_pipeline(category="restaurant", location="Dar es Salaam", max_results=3)
    for r in reports:
        print(r)
        print("=" * 60)
    if map_path:
        print(f"Map saved to {map_path}")
