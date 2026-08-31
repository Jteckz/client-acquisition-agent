"""
Outreach drafting agent: produces channel-specific draft messages.

Always saves drafts with status = "Pending Approval". This agent NEVER
sends anything and NEVER advances a draft beyond Pending Approval — only a
human can do that via the CLI approve/reject/mark-sent commands.
"""
from __future__ import annotations

import logging

from discovery.models import OutreachDraft
from llm.client import Role, get_llm_client
from llm.prompts import (
    EMAIL_DRAFT_PROMPT,
    FOLLOWUP_CONTEXT_TEMPLATE,
    LINKEDIN_MESSAGE_PROMPT,
    WHATSAPP_DRAFT_PROMPT,
)

logger = logging.getLogger(__name__)

CHANNEL_PROMPTS = {
    "email": EMAIL_DRAFT_PROMPT,
    "linkedin": LINKEDIN_MESSAGE_PROMPT,
    "whatsapp": WHATSAPP_DRAFT_PROMPT,
}


def draft_outreach(
    place_id: str,
    channel: str,
    business_name: str,
    hook: str,
    original_body: str | None = None,
    role: Role = "reasoning",
) -> OutreachDraft:
    """Draft a first-contact (or follow-up) message for one channel.

    `original_body` is passed only for follow-ups, so the follow-up can
    reference the earlier message without repeating it verbatim.

    `role` selects the model tier: first-contact drafting defaults to
    reasoning (writing quality matters); follow-ups pass the escalated role
    decided by analysis.followup_agent.
    """
    if channel not in CHANNEL_PROMPTS:
        raise ValueError(f"Unsupported channel '{channel}'. Use one of: {', '.join(CHANNEL_PROMPTS)}")

    followup_context = ""
    if original_body:
        followup_context = FOLLOWUP_CONTEXT_TEMPLATE.format(original_body=original_body)

    prompt = CHANNEL_PROMPTS[channel].format(
        business_name=business_name,
        hook=hook,
        followup_context=followup_context,
    )

    llm = get_llm_client(role=role)
    result = llm.generate_json(prompt)

    subject = result.get("subject") if channel == "email" else None
    body = str(result.get("body", "")).strip()

    # Small Llama models occasionally truncate mid-JSON. Retry once before
    # falling back to a placeholder the human can rewrite.
    if not body:
        logger.warning("Empty body on first draft attempt for %s — retrying once.", channel)
        result = llm.generate_json(prompt)
        subject = result.get("subject") if channel == "email" else subject
        body = str(result.get("body", "")).strip()

    return OutreachDraft(
        place_id=place_id,
        channel=channel,
        subject=subject,
        personalization_hook=hook,
        body=body or "[Draft failed to generate — please rewrite manually]",
        status="Pending Approval",
    )
