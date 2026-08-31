"""Phase 6 — CRM + response logging (V3): status mapping and CLI guard.

Also exercises the real CLI handler `cmd_log_response`: it must refuse to
log a reply against a draft that was never approved/sent, and must classify
+ persist + update the CRM for a sent draft.
"""
from __future__ import annotations

import argparse
import unittest

from storage.db import (
    get_crm_lead,
    get_responses,
    save_business,
    save_outreach_draft,
    update_crm_after_response,
)

from tests.helpers import TempDBTestCase, make_business, patch_llm


def _draft(**overrides):
    from discovery.models import OutreachDraft

    defaults = dict(
        place_id="node/1", channel="email", personalization_hook="h",
        body="b", status="Pending Approval",
    )
    defaults.update(overrides)
    return OutreachDraft(**defaults)


class CrmMappingTest(TempDBTestCase):
    def setUp(self):
        super().setUp()
        save_business(make_business(place_id="node/1", name="Test Cafe"))

    def test_all_five_statuses_map_to_crm(self):
        expectations = {
            "Warm Lead": ("Warm", "High"),
            "Future Opportunity": ("Future Opportunity", "Medium"),
            "Not Interested": ("Not Interested", "Low"),
            "Needs More Info": ("Warm", "Medium"),
            "Converted": ("Won", "High"),
        }
        for status, (pipeline, interest) in expectations.items():
            update_crm_after_response("node/1", status)
            row = get_crm_lead("node/1")
            self.assertEqual(row["pipeline_status"], pipeline, f"status={status}")
            self.assertEqual(row["interest_level"], interest, f"status={status}")

    def test_response_round_trip(self):
        from storage.db import save_response

        did = save_outreach_draft(_draft())
        save_response("node/1", did, "We are interested.", "Warm Lead")
        rows = get_responses("node/1")
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["classified_status"], "Warm Lead")
        self.assertEqual(rows[0]["response_text"], "We are interested.")


class LogResponseCliTest(TempDBTestCase):
    def setUp(self):
        super().setUp()
        save_business(make_business(place_id="node/1", name="Test Cafe"))

    def _run_cmd(self, draft_id, text):
        import main

        return main.cmd_log_response(argparse.Namespace(draft_id=draft_id, text=text))

    def test_pending_draft_refused(self):
        did = save_outreach_draft(_draft())
        with self.assertRaises(SystemExit):
            self._run_cmd(did, "hello")

    def test_sent_draft_classifies_and_updates_crm(self):
        did = save_outreach_draft(_draft(status="Sent"))
        with patch_llm([("Reply text:", {"status": "Converted"})]):
            self._run_cmd(did, "We want to proceed!")
        row = get_crm_lead("node/1")
        self.assertEqual(row["pipeline_status"], "Won")
        self.assertEqual(len(get_responses("node/1")), 1)

    def test_unknown_draft_refused(self):
        with self.assertRaises(SystemExit):
            self._run_cmd(999, "hello")


if __name__ == "__main__":
    unittest.main()