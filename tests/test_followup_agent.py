"""Phase 7 — Follow-up scheduling (V3): rule-based trigger + draft.

A lead is due for follow-up only when it was Contacted more than
FOLLOWUP_AFTER_DAYS ago AND has no logged response since contact. Leads with
a response (or fresh contacts) are excluded. Follow-up drafts reuse the
human-approval flow and require a prior SENT draft on the channel.
"""
from __future__ import annotations

import unittest

from datetime import date, timedelta

from analysis.followup_agent import draft_followup, list_leads_due_for_followup
from discovery.models import OutreachDraft
from storage.db import (
    get_connection,
    save_business,
    save_outreach_draft,
    save_response,
)

from tests.helpers import TempDBTestCase, make_business, patch_llm

NEXT = (date.today() + timedelta(days=7)).isoformat()


def _crm(place_id, last_contact):
    from storage.db import save_crm_lead

    save_crm_lead(
        place_id,
        pipeline_status="Contacted",
        last_contact_date=last_contact,
        next_follow_up_date=NEXT,
    )


class FollowupTriggerTest(TempDBTestCase):
    def _seed(self, place_id, name, last_contact):
        save_business(make_business(place_id=place_id, name=name))
        _crm(place_id, last_contact)

    def test_lead_contacted_past_window_is_due(self):
        self._seed("node/old", "Old Cafe", (date.today() - timedelta(days=10)).isoformat())
        due = list_leads_due_for_followup()
        self.assertEqual([l["place_id"] for l in due], ["node/old"])

    def test_fresh_contact_not_due(self):
        self._seed("node/fresh", "Fresh Cafe", date.today().isoformat())
        self.assertEqual(list_leads_due_for_followup(), [])

    def test_responded_lead_excluded_even_if_old(self):
        self._seed("node/old", "Old Cafe", (date.today() - timedelta(days=10)).isoformat())
        sent = save_outreach_draft(OutreachDraft(
            place_id="node/old", channel="email", personalization_hook="h",
            body="b", status="Sent",
        ))
        save_response("node/old", sent, "We replied", "Warm Lead")
        self.assertEqual(list_leads_due_for_followup(), [])

    def test_days_parameter_overrides_setting(self):
        self._seed("node/a", "A", (date.today() - timedelta(days=3)).isoformat())
        due = list_leads_due_for_followup(days=2)
        self.assertEqual([l["place_id"] for l in due], ["node/a"])


class DraftFollowupTest(TempDBTestCase):
    def test_requires_prior_sent_draft_on_channel(self):
        save_business(make_business(place_id="node/1"))
        with self.assertRaises(ValueError):
            draft_followup("node/1", "email")

    def test_drafts_followup_from_prior_message(self):
        save_business(make_business(place_id="node/1", name="Test Cafe"))
        prior = save_outreach_draft(OutreachDraft(
            place_id="node/1", channel="email", personalization_hook="We noticed you have no website.",
            body="Original message body.", status="Sent",
        ))

        with patch_llm([("Personalization hook", {"body": "Follow-up body"})]) as fake:
            draft = draft_followup("node/1", "email")
            prompt = fake.generate_json_calls[0]

        self.assertIsNotNone(draft)
        self.assertEqual(draft.status, "Pending Approval")
        self.assertIn("Original message body.", prompt)  # references the earlier message
        self.assertIsNotNone(prior)


if __name__ == "__main__":
    unittest.main()