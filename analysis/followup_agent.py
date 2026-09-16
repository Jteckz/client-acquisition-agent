"""
Follow-up agent: deterministic trigger + LLM draft, with the same
human-approval flow as first-contact outreach.

Trigger is rule-based (lead Contacted > FOLLOWUP_AFTER_DAYS ago with no
logged response). The draft reuses the channel-specific outreach prompts
with a follow-up instruction that references the original message.
"""
from __future__ import annotations

import logging

from analysis.outreach_drafter import draft_outreach
from config.settings import settings
from discovery.models import OutreachDraft
from llm.client import Role
from llm.prompts import PERSONALIZATION_HOOK_PROMPT  # noqa: F401  (documented reuse; hook reuse below)
from storage.db import (
    get_business,
    get_latest_problems,
    get_latest_qualification_score,
    get_latest_sent_draft,
    get_leads_due_for_followup,
)

logger = logging.getLogger(__name__)


def list_leads_due_for_followup(days: int | None = None) -> list:
    return get_leads_due_for_followup(days)


def draft_followup(place_id: str, channel: str) -> OutreachDraft | None:
    """Draft a follow-up for a lead that has a prior SENT draft on this channel."""
    prior = get_latest_sent_draft(place_id, channel)
    if prior is None:
        raise ValueError(
            f"No previously sent {channel} outreach found for {place_id} — cannot draft a follow-up."
        )

    business = get_business(place_id)
    if business is None:
        raise ValueError(f"Unknown business {place_id}.")

    hook = prior["personalization_hook"] or "Following up on our earlier message."
    draft = draft_outreach(
        place_id=place_id,
        channel=channel,
        business_name=business["name"],
        hook=hook,
        original_body=prior["body"],
        role=_followup_role(place_id),
    )
    return draft


def _followup_role(place_id: str) -> Role:
    """Escalate high-value leads to the reasoning model for follow-ups.

    Follow-ups are normally worker-tier (templated, repetitive writing), but
    a lead whose stored opportunity/qualification score exceeds
    FOLLOWUP_ESCALATION_SCORE gets the stronger model. Uses the score the
    existing V3 pipeline already computes and stores during discovery — no
    new scoring happens here. Leads with no stored score default to worker.
    """
    score = get_latest_qualification_score(place_id)
    if score is not None and score > settings.FOLLOWUP_ESCALATION_SCORE:
        logger.info(
            "Escalating follow-up for %s to reasoning model (score %d > %d)",
            place_id, score, settings.FOLLOWUP_ESCALATION_SCORE,
        )
        return "reasoning"
    return "worker"
