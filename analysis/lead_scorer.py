"""
Deterministic lead scoring.

Deliberately NOT an LLM call: asking a small Llama model to output a
consistent 0-100 number produces noisy, unreproducible scores. Instead we
turn qualitative signals (already extracted by research + problem
detection) into points via fixed rules. This is easy to explain, easy to
tune, and gives identical output for identical input.

Signals come from OpenStreetMap + a live website/social check — there's no
review data source in V1 (see research/reviews_analyzer.py), so scoring
leans on website quality, social presence, and contact-info completeness
as proxies for "is this a real, active business with a digital gap".
"""
from __future__ import annotations

from discovery.models import ProblemAnalysis, ResearchBundle, SolutionRecommendation

MAX_SCORE = 100

# Point values — tune these as you calibrate against real results.
POINTS = {
    "no_website": 25,
    "not_mobile_friendly": 10,
    "missing_online_ordering": 15,
    "missing_online_booking": 10,
    "no_social_presence": 15,
    "established_business": 10,  # has phone + address on record -> real, findable business
    "high_value_solution": 10,
}

VALUE_BONUS = {"High": 15, "Medium": 8, "Low": 0, "Unknown": 0}


def score_lead(
    bundle: ResearchBundle,
    problems: ProblemAnalysis,
    solutions: SolutionRecommendation,
) -> tuple[int, str, list[str]]:
    """Returns (score, priority, reasons)."""
    score = 0
    reasons: list[str] = []

    if not bundle.website.has_website:
        score += POINTS["no_website"]
        reasons.append("No website found")
    elif bundle.website.is_mobile_friendly is False:
        score += POINTS["not_mobile_friendly"]
        reasons.append("Website is not mobile-friendly")

    if bundle.website.has_website:
        if "online_ordering" in bundle.website.signals_missing:
            score += POINTS["missing_online_ordering"]
            reasons.append("No online ordering")
        if "online_booking" in bundle.website.signals_missing:
            score += POINTS["missing_online_booking"]
            reasons.append("No online booking")

    has_social = bool(bundle.social.platforms_found)
    if not has_social:
        score += POINTS["no_social_presence"]
        reasons.append("No active social media presence detected")

    if bundle.business.phone and bundle.business.address:
        score += POINTS["established_business"]
        reasons.append("Established business (phone + address on record)")

    if solutions.potential_value in VALUE_BONUS:
        bonus = VALUE_BONUS[solutions.potential_value]
        if bonus:
            score += bonus
            reasons.append(f"LLM-estimated potential value: {solutions.potential_value}")

    score = min(score, MAX_SCORE)
    priority = _priority_for_score(score)
    return score, priority, reasons


def _priority_for_score(score: int) -> str:
    if score >= 70:
        return "High"
    if score >= 40:
        return "Medium"
    return "Low"
