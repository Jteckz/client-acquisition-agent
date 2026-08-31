"""
Outreach preparation: produce the specific, evidence-based hook that opens
a message.

The hook must reference a concrete finding from the business's own data,
not a generic template phrase. The generated hook is validated against a
simple heuristic (does it share key terms with the detected problems?);
if not, the LLM is asked once more before falling back to a safe default.
"""
from __future__ import annotations

import logging
import re
from typing import Optional

from discovery.models import ProblemAnalysis, ResearchBundle
from llm.client import get_llm_client
from llm.prompts import PERSONALIZATION_HOOK_PROMPT

logger = logging.getLogger(__name__)

STOPWORDS = {
    "a", "an", "the", "and", "or", "but", "for", "with", "their", "that",
    "this", "your", "you", "has", "have", "had", "was", "were", "are",
    "not", "no", "lack", "needs", "need", "from", "they", "them", "its",
}


def prepare_hook(business_name: str, category: str, problems: ProblemAnalysis, bundle: Optional[ResearchBundle] = None) -> str:
    llm = get_llm_client(role="reasoning")
    evidence = _build_evidence(bundle) if bundle else "No additional evidence available."

    prompt = PERSONALIZATION_HOOK_PROMPT.format(
        business_name=business_name,
        category=category,
        problems="\n".join(f"- {p}" for p in problems.problems) if problems.problems else "No specific problems identified.",
        evidence=evidence,
    )

    # Try twice (spec: reject and retry once) when the hook doesn't reference
    # a real finding; then fall back to a safe, honest default.
    for _ in range(2):
        result = llm.generate_json(prompt)
        hook = str(result.get("hook", "")).strip()
        if hook and _references_findings(hook, problems.problems):
            return hook
        if not hook:
            continue
        logger.info("Hook lacked a reference to detected problems; asking once more.")

    if problems.problems:
        return f"Noticing {business_name} could use help with {problems.problems[0].lower()}."
    return f"Seeing ways {business_name} could grow its digital presence."


def _references_findings(hook: str, problems: list[str]) -> bool:
    hook_l = hook.lower()
    for problem in problems:
        for word in _significant_words(problem):
            if word in hook_l:
                return True
    return False


def _significant_words(text: str) -> set[str]:
    words = re.findall(r"[a-z]+", text.lower())
    return {w for w in words if len(w) > 3 and w not in STOPWORDS}


def _build_evidence(bundle: ResearchBundle) -> str:
    lines = []
    w = bundle.website
    if not w.has_website:
        lines.append("- No website found.")
    else:
        lines.append(f"- Website reachable: {w.reachable}; mobile-friendly: {w.is_mobile_friendly}.")
        if w.signals_found:
            lines.append(f"- Website features found: {', '.join(w.signals_found)}.")
        if w.signals_missing:
            lines.append(f"- Website features missing: {', '.join(w.signals_missing)}.")
    if bundle.social.platforms_found:
        lines.append(f"- Reachable social platforms: {', '.join(bundle.social.platforms_found)}.")
    else:
        lines.append("- No reachable social media presence.")
    if bundle.reviews.common_complaints:
        lines.append(f"- Review complaints: {', '.join(bundle.reviews.common_complaints)}.")
    return "\n".join(lines) or "No additional evidence available."
