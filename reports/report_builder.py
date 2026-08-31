"""Assembles the final LeadReport object and renders it to markdown text."""
from __future__ import annotations

from pathlib import Path

from jinja2 import Environment, FileSystemLoader

from analysis.lead_scorer import score_lead
from analysis.problem_detector import detect_problems
from analysis.solution_recommender import recommend_solutions
from discovery.models import LeadReport, ResearchBundle
from research.presence_summarizer import summarize_presence

TEMPLATE_DIR = Path(__file__).resolve().parent / "templates"
_env = Environment(loader=FileSystemLoader(str(TEMPLATE_DIR)), trim_blocks=True, lstrip_blocks=True)


def build_lead_report(bundle: ResearchBundle) -> LeadReport:
    """Runs presence summary -> problem detection -> recommendation -> scoring.

    The worker-model presence summary is fed into problem detection as
    additional context, not a replacement for the structured findings.
    """
    presence_summary = summarize_presence(bundle)
    problems = detect_problems(bundle, presence_summary=presence_summary)
    solutions = recommend_solutions(bundle.business, problems)
    score, priority, reasons = score_lead(bundle, problems, solutions)

    return LeadReport(
        business=bundle.business,
        website=bundle.website,
        reviews=bundle.reviews,
        social=bundle.social,
        problems=problems.problems,
        solutions=solutions.solutions,
        potential_value=solutions.potential_value,
        lead_score=score,
        priority=priority,
        score_reasons=reasons,
    )


def render_report(report: LeadReport) -> str:
    template = _env.get_template("report.md.j2")
    return template.render(**report.model_dump())
