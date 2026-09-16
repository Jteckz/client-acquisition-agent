from __future__ import annotations

import logging
from pathlib import Path

from jinja2 import Environment, FileSystemLoader
from weasyprint import HTML

from analysis.cost_estimator import estimate_cost
from analysis.lead_qualifier import qualify_lead
from analysis.solution_designer import design_solution
from analysis.tech_recommender import recommend_tech_stack
from config.settings import settings
from discovery.models import (
    Business,
    CostEstimate,
    ProblemAnalysis,
    ProposalDocument,
    QualificationScore,
    ResearchBundle,
    SolutionBlueprint,
    TechStack,
)
from llm.client import get_llm_client
from llm.prompts import EXECUTIVE_SUMMARY_PROMPT

logger = logging.getLogger(__name__)

TEMPLATE_DIR = Path(__file__).resolve().parent / "templates"
_env = Environment(loader=FileSystemLoader(str(TEMPLATE_DIR)), trim_blocks=True, lstrip_blocks=True)


def _comma(value: int) -> str:
    return f"{value:,}"


_env.filters["comma"] = _comma


def generate_proposal(bundle: ResearchBundle, problems: ProblemAnalysis) -> ProposalDocument | None:
    qualification = qualify_lead(bundle, problems)
    if qualification.total_score < settings.MIN_QUALIFICATION_SCORE_FOR_PROPOSAL:
        logger.info(
            "Skipping proposal for %s — qualification score %d below threshold %d",
            bundle.business.name, qualification.total_score, settings.MIN_QUALIFICATION_SCORE_FOR_PROPOSAL,
        )
        return None

    blueprint, template = design_solution(bundle.business.category, problems)
    tech_stack = recommend_tech_stack(bundle.business.category, blueprint, template)
    cost_est = estimate_cost(blueprint, template)
    exec_summary = _generate_executive_summary(bundle.business, blueprint, problems)

    expected_benefits = _derive_benefits(problems, blueprint)

    doc = ProposalDocument(
        business_name=bundle.business.name,
        executive_summary=exec_summary,
        identified_challenges=problems.problems,
        proposed_solution=blueprint,
        tech_stack=tech_stack,
        cost_estimate=cost_est,
        expected_benefits=expected_benefits,
    )

    pdf_path = _render_pdf(doc, bundle.business)
    doc.pdf_path = pdf_path
    doc.status = "Ready for Outreach"

    return doc


def _generate_executive_summary(business: Business, blueprint: SolutionBlueprint, problems: ProblemAnalysis) -> str:
    llm = get_llm_client(role="reasoning")
    prompt = EXECUTIVE_SUMMARY_PROMPT.format(
        business_name=business.name,
        category=business.category,
        challenges="; ".join(problems.problems) if problems.problems else "Limited digital presence",
        package_name=blueprint.package_name,
        features=", ".join(blueprint.features),
    )
    return llm.generate(prompt).strip()


def _derive_benefits(problems: ProblemAnalysis, blueprint: SolutionBlueprint) -> list[str]:
    benefits = []
    for feature in blueprint.features:
        benefits.append(f"Increased customer reach through {feature.lower()}")
    if problems.problems:
        benefits.append(f"Addresses key challenge: {problems.problems[0]}")
    return benefits


def _render_pdf(doc: ProposalDocument, business: Business) -> str:
    slug = business.name.lower().replace(" ", "_").replace("/", "_")[:50]
    out_dir = Path(settings.PROPOSALS_OUTPUT_DIR)
    out_dir.mkdir(parents=True, exist_ok=True)
    pdf_path = out_dir / f"{slug}.pdf"

    html_str = _render_html(doc, business)
    HTML(string=html_str).write_pdf(str(pdf_path))
    logger.info("Saved proposal PDF to %s", pdf_path)
    return str(pdf_path)


def _render_html(doc: ProposalDocument, business: Business) -> str:
    template = _env.get_template("proposal.html.j2")
    return template.render(
        business_name=business.name,
        category=business.category,
        summary=doc.executive_summary,
        challenges=doc.identified_challenges,
        package_name=doc.proposed_solution.package_name,
        features=doc.proposed_solution.features,
        frontend=doc.tech_stack.frontend,
        backend=doc.tech_stack.backend,
        database=doc.tech_stack.database,
        hosting=doc.tech_stack.hosting,
        cost_min=doc.cost_estimate.estimated_cost_min,
        cost_max=doc.cost_estimate.estimated_cost_max,
        weeks_min=doc.cost_estimate.estimated_weeks_min,
        weeks_max=doc.cost_estimate.estimated_weeks_max,
        currency=doc.cost_estimate.currency,
        benefits=doc.expected_benefits,
    )
