"""
Digital-presence summarization (worker model).

Sits between the raw research checks (website/social/reviews — all
deterministic) and problem detection. Condenses the raw findings into a
short plain-language summary that the reasoning model can parse quickly,
so the problem-detection prompt is shorter and more focused without losing
information (the structured findings are still passed through).

This is intentionally a worker-tier task: simple condensation, no business
reasoning.
"""
from __future__ import annotations

from discovery.models import ResearchBundle
from llm.client import get_llm_client
from llm.prompts import PRESENCE_SUMMARY_PROMPT


def summarize_presence(bundle: ResearchBundle) -> str:
    """Return a 1-2 sentence plain-language summary of the online presence."""
    llm = get_llm_client(role="worker")
    prompt = PRESENCE_SUMMARY_PROMPT.format(
        website_summary=_summarize_website(bundle),
        social_summary=_summarize_social(bundle),
    )
    return llm.generate(prompt).strip()


def _summarize_website(bundle: ResearchBundle) -> str:
    w = bundle.website
    if not w.has_website:
        return "No website found."
    if not w.reachable:
        return "Website exists but could not be reached during the check."
    bits = []
    if w.is_mobile_friendly is not None:
        bits.append("mobile-friendly" if w.is_mobile_friendly else "not mobile-friendly")
    if w.has_ssl:
        bits.append("HTTPS enabled")
    if w.signals_found:
        bits.append(f"features found: {', '.join(w.signals_found)}")
    if w.signals_missing:
        bits.append(f"features missing: {', '.join(w.signals_missing)}")
    return "Reachable website; " + "; ".join(bits) + "."


def _summarize_social(bundle: ResearchBundle) -> str:
    s = bundle.social
    if s.platforms_found:
        return f"Reachable on {', '.join(s.platforms_found)}."
    if s.platforms_missing:
        return f"No reachable social presence; expected platforms not found ({', '.join(s.platforms_missing)})."
    return "No social media presence found."
