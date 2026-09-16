"""
Response intelligence: classify a human-pasted reply into a fixed enum.

Takes raw reply text only — this module never fetches messages from an
inbox or messaging API. The classified status is validated against a fixed
list; an invalid LLM label is never allowed to reach the CRM.
"""
from __future__ import annotations

import logging

from llm.client import get_llm_client
from llm.prompts import RESPONSE_CLASSIFICATION_PROMPT

logger = logging.getLogger(__name__)

RESPONSE_STATUSES = [
    "Warm Lead", "Future Opportunity", "Not Interested",
    "Needs More Info", "Converted",
]

FALLBACK_STATUS = "Needs More Info"


def classify_response(response_text: str) -> str:
    llm = get_llm_client(role="worker")
    prompt = RESPONSE_CLASSIFICATION_PROMPT.format(response_text=response_text)
    result = llm.generate_json(prompt)
    status = str(result.get("status", "")).strip()

    # Small models sometimes echo extra words after a valid label
    # (e.g. "Future Opportunity: interested but not ready now"). Accept the
    # label prefix deterministically; only fully-unrecognized output falls back.
    for candidate in RESPONSE_STATUSES:
        if status == candidate or status.startswith(candidate):
            if status != candidate:
                logger.info("Normalized response status %r -> %r", status, candidate)
            return candidate

    logger.warning(
        "LLM returned invalid response status %r — falling back to %r",
        status, FALLBACK_STATUS,
    )
    return FALLBACK_STATUS
