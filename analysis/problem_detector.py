"""Turns raw research findings into a concrete list of business problems."""
from __future__ import annotations

from discovery.models import ProblemAnalysis, ResearchBundle
from llm.client import get_llm_client
from llm.prompts import PROBLEM_DETECTION_PROMPT


def detect_problems(bundle: ResearchBundle) -> ProblemAnalysis:
    llm = get_llm_client()

    prompt = PROBLEM_DETECTION_PROMPT.format(
        business_name=bundle.business.name,
        category=bundle.business.category,
        website_findings=_summarize_website(bundle),
        review_findings=_summarize_reviews(bundle),
        social_findings=_summarize_social(bundle),
    )

    result = llm.generate_json(prompt)
    return ProblemAnalysis(
        problems=result.get("problems", []),
        reasoning=result.get("reasoning", ""),
    )


def _summarize_website(bundle: ResearchBundle) -> str:
    w = bundle.website
    if not w.has_website:
        return "No website found."
    lines = [
        f"Reachable: {w.reachable}",
        f"Mobile-friendly: {w.is_mobile_friendly}",
        f"HTTPS: {w.has_ssl}",
        f"Features found: {', '.join(w.signals_found) or 'none'}",
        f"Features missing: {', '.join(w.signals_missing) or 'none'}",
    ]
    return "\n".join(lines)


def _summarize_reviews(bundle: ResearchBundle) -> str:
    r = bundle.reviews
    if r.review_count_analyzed == 0:
        return "No reviews available."
    lines = [
        f"Reviews analyzed: {r.review_count_analyzed}",
        f"Average rating: {r.average_rating}",
        f"Common complaints: {', '.join(r.common_complaints) or 'none'}",
        f"Positive themes: {', '.join(r.positive_themes) or 'none'}",
    ]
    return "\n".join(lines)


def _summarize_social(bundle: ResearchBundle) -> str:
    s = bundle.social
    lines = [
        f"Platforms found: {', '.join(s.platforms_found) or 'none'}",
        f"Platforms missing: {', '.join(s.platforms_missing) or 'none'}",
    ]
    return "\n".join(lines)
