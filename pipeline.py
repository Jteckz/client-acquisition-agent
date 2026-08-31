"""
Orchestrates the full V1+V2 workflow.

  V1: discover -> research -> detect problems -> recommend solutions -> score -> report
  V2: qualify -> design solution -> recommend tech stack -> estimate cost -> generate proposal PDF
"""
from __future__ import annotations

import logging

from discovery.models import Business, LeadReport, ProposalDocument, ResearchBundle
from discovery.osm_places import parse_query, search_businesses
from research.reviews_analyzer import analyze_reviews
from research.social_checker import check_social_presence
from research.website_checker import check_website
from reports.map_builder import build_leads_map
from reports.report_builder import build_lead_report, render_report
from storage.db import init_db, save_business, save_crm_lead, save_lead_report

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
    generate_proposals: bool = False,
) -> tuple[list[str], list[LeadReport], str | None, list[ProposalDocument]]:
    """
    Full pipeline for one search. Pass either `query` (e.g. "restaurants in
    Dar es Salaam") OR explicit `category`/`location`.

    V1 always runs. When generate_proposals=True, V2 qualification ->
    design -> cost -> proposal PDF runs for each lead above the minimum
    qualification threshold.

    Returns (rendered_markdown_reports, LeadReport_objects, path_to_map_html, ProposalDocument_list).
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
    proposals: list[ProposalDocument] = []

    for business in businesses:
        try:
            save_business(business)
            save_crm_lead(business.place_id)  # ensure a CRM record exists (status New)
            bundle = research_business(business)
            report = build_lead_report(bundle)
            save_lead_report(report)
            rendered_reports.append(render_report(report))
            lead_reports.append(report)
            logger.info(
                "Scored %s: %d/100 (%s)", business.name, report.lead_score, report.priority
            )

            # V3 signals are cheap and deterministic — persist them for every
            # lead so ranking/outreach commands work without re-discovery.
            from analysis.lead_qualifier import qualify_lead
            from discovery.models import ProblemAnalysis
            from research.contact_finder import find_reachability
            from storage.db import save_qualification_score, save_reachability

            problems = ProblemAnalysis(problems=report.problems)
            save_qualification_score(business.place_id, qualify_lead(bundle, problems))
            save_reachability(business.place_id, find_reachability(bundle))

            if generate_proposals:
                proposal = _run_v2(bundle, report)
                if proposal:
                    proposals.append(proposal)
        except Exception:
            logger.exception("Failed to process business: %s", business.name)
            continue

    map_path = build_leads_map(lead_reports) if lead_reports else None
    return rendered_reports, lead_reports, map_path, proposals


def _run_v2(bundle: ResearchBundle, report: LeadReport) -> ProposalDocument | None:
    from analysis.problem_detector import ProblemAnalysis
    from reports.proposal_builder import generate_proposal as _gen_proposal
    from storage.db import save_proposal as _save_proposal

    problems = ProblemAnalysis(problems=report.problems)

    proposal = _gen_proposal(bundle, problems)
    if proposal is None:
        return None

    _save_proposal(bundle.business.place_id, proposal)
    logger.info(
        "Generated proposal for %s: %s ($%d–$%d, %d–%d weeks)",
        bundle.business.name, proposal.proposed_solution.package_name,
        proposal.cost_estimate.estimated_cost_min, proposal.cost_estimate.estimated_cost_max,
        proposal.cost_estimate.estimated_weeks_min, proposal.cost_estimate.estimated_weeks_max,
    )
    return proposal


if __name__ == "__main__":
    # Quick manual smoke test — prefer `python main.py` for real usage.
    reports, _, map_path = run_pipeline(category="restaurant", location="Dar es Salaam", max_results=3)
    for r in reports:
        print(r)
        print("=" * 60)
    if map_path:
        print(f"Map saved to {map_path}")
