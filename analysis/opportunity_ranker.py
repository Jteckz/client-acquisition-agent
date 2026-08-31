"""
Opportunity ranking engine.

Deterministic, rule-based — follows the project rule that numbers are never
trusted raw from the LLM. This combines V2's qualification sub-scores (need
and budget) with the V3 reachability score so that a highly reachable,
decently-budgeted lead can rank above a high-need, low-reachability one.

Normalization: each sub-score is scaled to a common 0-100 range first, then
weighted. Final score is clipped to [0, 100].
"""
from __future__ import annotations

import logging

from discovery.models import OpportunityRanking, QualificationScore, ReachabilityInfo

logger = logging.getLogger(__name__)

WEIGHTS = {"need": 0.4, "budget": 0.4, "reachability": 0.2}

# Maximum raw values of each qualification sub-score (used for normalization).
NEED_MAX = 35
BUDGET_MAX = 30


def rank_opportunity(
    qualification: QualificationScore, reachability: ReachabilityInfo
) -> OpportunityRanking:
    need_norm = _normalize(qualification.solution_need_score, NEED_MAX)
    budget_norm = _normalize(qualification.ability_to_pay_score, BUDGET_MAX)
    reach_norm = _normalize(reachability.reachability_score, 100)

    final = round(
        need_norm * WEIGHTS["need"]
        + budget_norm * WEIGHTS["budget"]
        + reach_norm * WEIGHTS["reachability"]
    )
    final = max(0, min(100, final))

    reasons = [
        f"Solution need: {qualification.solution_need_score}/{NEED_MAX}",
        f"Budget signal: {qualification.ability_to_pay_score}/{BUDGET_MAX}",
        f"Reachability: {reachability.reachability_score}/100",
        f"Channels: {', '.join(reachability.contactable_channels) or 'none'}",
    ]

    return OpportunityRanking(
        need_score=qualification.solution_need_score,
        budget_score=qualification.ability_to_pay_score,
        reachability_score=reachability.reachability_score,
        final_score=final,
        rank_reasoning=reasons,
    )


def _normalize(raw: int, max_value: int) -> float:
    """Scale a raw sub-score to 0-100, guarding against max_value of 0."""
    if max_value <= 0:
        return 0.0
    scaled = raw / max_value * 100
    return max(0.0, min(100.0, scaled))


def rank_all(limit: int = 20) -> list[tuple[str, str, OpportunityRanking]]:
    """Compute/refresh rankings for all leads with qualification scores.

    Reachability is loaded from storage (populated during discovery). Leads
    with no stored reachability get a fresh check by re-running the research
    step (which may require network access).
    """
    from discovery.models import Business, QualificationScore, ReachabilityInfo
    from pipeline import research_business
    from research.contact_finder import find_reachability
    from storage.db import (
        get_business,
        get_rankable_rows,
        get_reachability,
        save_opportunity_ranking,
        save_reachability,
    )

    rankings: list[tuple[str, str, OpportunityRanking]] = []
    for row in get_rankable_rows():
        place_id = row["place_id"]

        reach = _load_reachability(get_reachability(place_id))
        if reach is None:
            business = get_business(place_id)
            if business is not None:
                try:
                    biz = Business(
                        place_id=business["place_id"],
                        name=business["name"],
                        category=business["category"] or "",
                        website=business["website"],
                        phone=business["phone"],
                        address=business["address"],
                        latitude=business["latitude"],
                        longitude=business["longitude"],
                    )
                    bundle = research_business(biz)
                    reach_model = find_reachability(bundle)
                    save_reachability(place_id, reach_model)
                    reach = ReachabilityInfo(
                        email_found=reach_model.email_found,
                        contactable_channels=reach_model.contactable_channels,
                        reachability_score=reach_model.reachability_score,
                    )
                except Exception:
                    logger.warning("Could not compute reachability for %s", place_id)
            if reach is None:
                reach = ReachabilityInfo(reachability_score=0)

        qual = QualificationScore(
            business_activity_score=0,
            digital_presence_score=0,
            ability_to_pay_score=row["ability_to_pay_score"],
            solution_need_score=row["solution_need_score"],
            total_score=0,
            priority="",
            reasoning=[],
        )

        ranking = rank_opportunity(qual, reach)
        save_opportunity_ranking(place_id, ranking)
        rankings.append((row["name"], row["category"], ranking))

    rankings.sort(key=lambda t: t[2].final_score, reverse=True)
    return rankings[:limit]


def _load_reachability(row) -> ReachabilityInfo | None:
    """Convert a stored reachability DB row into a model, or None."""
    if row is None:
        return None
    import json as _json
    try:
        channels = _json.loads(row["contactable_channels_json"] or "[]")
    except ValueError:
        channels = []
    return ReachabilityInfo(
        email_found=row["email_found"],
        contactable_channels=channels,
        reachability_score=row["reachability_score"] or 0,
    )
