"""Phase 6 — Human sends & response logging (V3): draft state machine.

The workflow under test is the README's strict lifecycle:
Pending Approval -> (human) Approve -> (human) Send -> (human) Log response.
Each transition is guarded: approval/rejection only from Pending, sending
only from Approved. The agent itself never advances a draft.
"""
from __future__ import annotations

import unittest

from datetime import date, timedelta

from storage.db import (
    approve_draft,
    get_crm_lead,
    get_outreach_draft,
    get_outreach_drafts,
    mark_draft_sent,
    reject_draft,
    save_business,
    save_outreach_draft,
)

from tests.helpers import TempDBTestCase, make_business


def _draft(**overrides):
    from discovery.models import OutreachDraft

    defaults = dict(
        place_id="node/1",
        channel="email",
        personalization_hook="hook",
        body="body",
        status="Pending Approval",
    )
    defaults.update(overrides)
    return OutreachDraft(**defaults)


class DraftWorkflowTest(TempDBTestCase):
    def setUp(self):
        super().setUp()
        save_business(make_business(place_id="node/1", name="Test Cafe"))

    def test_new_draft_starts_pending_approval(self):
        did = save_outreach_draft(_draft())
        row = get_outreach_draft(did)
        self.assertEqual(row["status"], "Pending Approval")

    def test_approve_transitions_to_approved(self):
        did = save_outreach_draft(_draft())
        row = approve_draft(did)
        self.assertEqual(row["status"], "Approved")
        self.assertIsNotNone(row["approved_at"])

    def test_cannot_approve_non_pending(self):
        did = save_outreach_draft(_draft())
        approve_draft(did)
        with self.assertRaises(ValueError):
            approve_draft(did)

    def test_reject_only_from_pending(self):
        did = save_outreach_draft(_draft())
        reject_draft(did)
        with self.assertRaises(ValueError):
            reject_draft(did)

    def test_mark_sent_requires_approved(self):
        did = save_outreach_draft(_draft())
        with self.assertRaises(ValueError):
            mark_draft_sent(did)

    def test_mark_sent_updates_crm_to_contacted_with_followup(self):
        did = save_outreach_draft(_draft())
        approve_draft(did)
        row = mark_draft_sent(did)
        self.assertEqual(row["status"], "Sent")
        self.assertIsNotNone(row["sent_at"])

        crm = get_crm_lead("node/1")
        self.assertEqual(crm["pipeline_status"], "Contacted")
        self.assertEqual(crm["last_contact_date"], date.today().isoformat())
        expected_next = (date.today() + timedelta(days=7)).isoformat()
        self.assertEqual(crm["next_follow_up_date"], expected_next)

    def test_unknown_draft_ids_raise_for_all_actions(self):
        for action in (approve_draft, reject_draft, mark_draft_sent):
            with self.assertRaises(ValueError):
                action(999)

    def test_list_drafts_filters_by_status(self):
        did = save_outreach_draft(_draft())
        pending = get_outreach_drafts("Pending Approval")
        self.assertEqual(len(pending), 1)
        self.assertEqual(pending[0]["id"], did)
        self.assertEqual(get_outreach_drafts("Sent"), [])


if __name__ == "__main__":
    unittest.main()