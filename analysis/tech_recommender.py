from __future__ import annotations

from typing import Any

from discovery.models import SolutionBlueprint, TechStack
from llm.client import get_llm_client
from llm.prompts import TECH_STACK_PROMPT

ALLOWED_STACKS: list[dict[str, str]] = [
    {"frontend": "React", "backend": "FastAPI", "database": "PostgreSQL", "hosting": "DigitalOcean"},
    {"frontend": "Flutter", "backend": "Django", "database": "PostgreSQL", "hosting": "DigitalOcean"},
    {"frontend": "Next.js", "backend": "Node/Express", "database": "MongoDB", "hosting": "Render"},
]


def recommend_tech_stack(category: str, blueprint: SolutionBlueprint, template: dict[str, Any] | None = None) -> TechStack:
    if template and "default_tech_stack" in template:
        default = template["default_tech_stack"]
        if default in ALLOWED_STACKS:
            return TechStack(**default, reasoning="Template default stack matched.")

    llm = get_llm_client(role="reasoning")
    allowed_str = "\n".join(
        f"{i+1}. frontend={s['frontend']}, backend={s['backend']}, database={s['database']}, hosting={s['hosting']}"
        for i, s in enumerate(ALLOWED_STACKS)
    )

    prompt = TECH_STACK_PROMPT.format(
        category=category,
        package_name=blueprint.package_name,
        features=", ".join(blueprint.features),
        allowed_stacks=allowed_str,
    )

    result = llm.generate_json(prompt)

    chosen = {
        "frontend": result.get("frontend", ""),
        "backend": result.get("backend", ""),
        "database": result.get("database", ""),
        "hosting": result.get("hosting", ""),
    }

    if not _is_allowed(chosen):
        return TechStack(**ALLOWED_STACKS[0], reasoning="LLM returned unallowed stack; fell back to default.")

    return TechStack(**chosen, reasoning=result.get("reasoning", ""))


def _is_allowed(stack: dict[str, str]) -> bool:
    return any(
        s["frontend"] == stack["frontend"]
        and s["backend"] == stack["backend"]
        and s["database"] == stack["database"]
        and s["hosting"] == stack["hosting"]
        for s in ALLOWED_STACKS
    )
