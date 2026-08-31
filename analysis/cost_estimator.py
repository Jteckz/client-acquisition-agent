from __future__ import annotations

from typing import Any

from discovery.models import ComplexityEstimate, CostEstimate, SolutionBlueprint
from llm.client import get_llm_client
from llm.prompts import COMPLEXITY_PROMPT

COMPLEXITY_MULTIPLIER = {"Low": 0.8, "Medium": 1.0, "High": 1.4}
DEFAULT_BASE_COST: list[int] = [1000, 2000]
DEFAULT_BASE_WEEKS: list[int] = [3, 5]


def estimate_cost(blueprint: SolutionBlueprint, template: dict[str, Any] | None) -> CostEstimate:
    complexity = _assess_complexity(blueprint)

    if template:
        base_cost: list[int] = template.get("base_cost_usd", DEFAULT_BASE_COST)
        base_weeks: list[int] = template.get("base_weeks", DEFAULT_BASE_WEEKS)
        template_base_features: list[str] = template.get("base_features", [])
    else:
        base_cost = DEFAULT_BASE_COST
        base_weeks = DEFAULT_BASE_WEEKS
        template_base_features = []

    mult = COMPLEXITY_MULTIPLIER.get(complexity.complexity, 1.0)
    extra_features = max(0, len(blueprint.features) - len(template_base_features))

    cost_min = round(base_cost[0] * mult + extra_features * 150)
    cost_max = round(base_cost[1] * mult + extra_features * 250)
    weeks_min = round(base_weeks[0] * mult)
    weeks_max = round(base_weeks[1] * mult) + (1 if extra_features > 2 else 0)

    return CostEstimate(
        complexity=complexity.complexity,
        estimated_weeks_min=weeks_min,
        estimated_weeks_max=weeks_max,
        estimated_cost_min=cost_min,
        estimated_cost_max=cost_max,
    )


def _assess_complexity(blueprint: SolutionBlueprint) -> ComplexityEstimate:
    # Simple Low/Medium/High classification of the feature list — worker-tier
    # work. All dollar/week math happens deterministically below in
    # estimate_cost, never in the model.
    llm = get_llm_client(role="worker")
    prompt = COMPLEXITY_PROMPT.format(
        features="\n".join(f"- {f}" for f in blueprint.features),
        feature_count=len(blueprint.features),
    )
    result = llm.generate_json(prompt)
    complexity = result.get("complexity", "Medium")
    if complexity not in COMPLEXITY_MULTIPLIER:
        complexity = "Medium"

    return ComplexityEstimate(
        complexity=complexity,
        feature_count=len(blueprint.features),
        reasoning=result.get("reasoning", ""),
    )
