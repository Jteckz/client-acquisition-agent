from __future__ import annotations

from typing import Any

from discovery.models import ProblemAnalysis, SolutionBlueprint
from llm.client import get_llm_client
from llm.prompts import SOLUTION_DESIGN_PROMPT
from solutions.library import load_template


def design_solution(category: str, problems: ProblemAnalysis) -> tuple[SolutionBlueprint, dict[str, Any] | None]:
    template = load_template(category)
    if template:
        features_str = "\n".join(f"- {f}" for f in template["base_features"])
        template_context = f"Available template '{template['package_name']}' with base features:\n{features_str}"
    else:
        template_context = "No template available — design from scratch."

    # Optional knowledge-base context. Empty unless this category has enough
    # contacted leads to say anything meaningful (see analysis/insights.py).
    insight_context = _insight_context(category)

    llm = get_llm_client(role="reasoning")
    prompt = SOLUTION_DESIGN_PROMPT.format(
        problems="\n".join(f"- {p}" for p in problems.problems) if problems.problems else "No specific problems identified.",
        template_context=template_context,
        insight_context=insight_context,
    )

    result = llm.generate_json(prompt)

    # The Solution Library is the single source of truth for package identity:
    # when a template exists its (already-validated) name wins over whatever
    # the model returned — the model only customizes features. Only a
    # template-less (custom) design accepts a model-chosen name.
    package_name = template["package_name"] if template else result.get("package_name", "Custom Solution")

    blueprint = SolutionBlueprint(
        package_name=package_name,
        features=result.get("features", []),
        reasoning=result.get("reasoning", ""),
    )
    return blueprint, template


def _insight_context(category: str) -> str:
    try:
        from analysis.insights import insight_context_for_category
        return insight_context_for_category(category)
    except Exception:
        return ""
