"""Maps detected problems to concrete software solution recommendations."""
from __future__ import annotations

from discovery.models import Business, ProblemAnalysis, SolutionRecommendation
from llm.client import get_llm_client
from llm.prompts import SOLUTION_RECOMMENDATION_PROMPT


def recommend_solutions(business: Business, analysis: ProblemAnalysis) -> SolutionRecommendation:
    if not analysis.problems:
        return SolutionRecommendation(solutions=[], potential_value="Low", reasoning="No problems detected.")

    llm = get_llm_client(role="reasoning")
    prompt = SOLUTION_RECOMMENDATION_PROMPT.format(
        business_name=business.name,
        category=business.category,
        problems="\n".join(f"- {p}" for p in analysis.problems),
    )

    result = llm.generate_json(prompt)
    return SolutionRecommendation(
        solutions=result.get("solutions", []),
        potential_value=result.get("potential_value", "Unknown"),
        reasoning=result.get("reasoning", ""),
    )
