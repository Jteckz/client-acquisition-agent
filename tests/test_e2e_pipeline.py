"""End-to-end: all eight README phases chained against a throwaway DB.

Everything that could reach a network or real LLM is substituted (fakes),
and requests.post is blocked outright — so if any code path tried to "send"
something, this test would fail loudly. The lifecycle runs:

  discover (P1-P4) -> rank (P4) -> prepare-outreach (P5, Pending Approval)
  -> approve (P6) -> mark-sent (P6, CRM Contacted) -> log-response (P6)
  -> follow-ups (P7) -> follow-up draft (P5/P7) -> insights + funnel (P8)

Run: python -m unittest tests.test_e2e_pipeline -v
"""
from __future__ import annotations

import argparse
import unittest
from datetime import date, timedelta
from unittest import mock

from analysis.followup_agent import list_leads_due_for_followup
from analysis.insights import category_conversion_stats
from discovery.models import OutreachDraft
from storage.db import (
    get_business,
    get_crm_lead,
    get_connection,
    get_funnel_metrics,
    get_outreach_drafts,
    save_outreach_draft,
)

from tests.helpers import TempDBTestCase, make_business, make_website, patch_llm, days_ago

FAKE_HTML = (
    '<html><head><meta name="viewport" content="width=device-width"></head>'
    '<body><a href="mailto:hello@cafe.co.tz">mail</a>'
    '<p>order now, wa.me/255700000000</p></body></html>'
)

LLM_RESPONSES = [
    # Phase 3: problem detection
    ("Website findings:", {
        "problems": ["No website found", "No online ordering"], "reasoning": "evidence",
    }),
    # Phase 3: solution recommendation
    ("Recommend specific", {
        "solutions": ["Website platform"], "potential_value": "Medium", "reasoning": "",
    }),
    # Phase 4: solution design (restaurant template)
    ("Available template", {
        "package_name": "Restaurant Digital Platform",
        "features": ["Website", "Digital Menu", "Online Ordering", "WhatsApp Integration"],
        "reasoning": "",
    }),
    # Phase 4: complexity estimate
    ("Number of features", {"complexity": "Medium", "reasoning": ""}),
    # Phase 5: personalization hook
    ("Evidence gathered:", {"hook": "We noticed Cafe One has no website."}),
    # Phase 5: channel draft
    ("Personalization hook", {
        "subject": "A website for Cafe One", "body": "Hi, open to a short call?",
    }),
    # Phase 6: response classification
    ("Reply text:", {"status": "Warm Lead", "reasoning": "interested"}),
]


class FakeHTML:
    def __init__(self, string=None, *args, **kwargs):
        self.string = string

    def write_pdf(self, path):
        with open(path, "w") as f:
            f.write(self.string or "")


class E2EPipelineTest(TempDBTestCase):
    def test_full_lifecycle_across_all_phases(self):
        biz1 = make_business(place_id="node/1", name="Cafe One", website="https://cafe.example")
        biz2 = make_business(place_id="node/2", name="Cafe Two", website="https://cafe2.example")

        with patch_llm(LLM_RESPONSES), \
             mock.patch("pipeline.search_businesses", return_value=[biz1, biz2]), \
             mock.patch("pipeline.build_leads_map", return_value=None), \
             mock.patch("research.website_checker.requests.get",
                        return_value=_FakeResp(FAKE_HTML)), \
             mock.patch("research.social_checker._url_reachable", return_value=True), \
             mock.patch("reports.proposal_builder.HTML", FakeHTML), \
             mock.patch("requests.post", side_effect=AssertionError("outbound post blocked")):

            # ── Phase 1-4: discover + research + detect/recommend + qualify/design/proposal
            import pipeline as pipe

            reports, lead_reports, map_path, proposals = pipe.run_pipeline(
                category="restaurant", location="Testville", max_results=2,
                generate_proposals=True,
            )
            self.assertEqual(len(reports), 2)
            self.assertEqual(len(lead_reports), 2)
            self.assertEqual(len(proposals), 2)
            self.assertEqual(proposals[0].status, "Ready for Outreach")
            self.assertIsNotNone(proposals[0].pdf_path)

            # every discovered business has a CRM row + qualification + reachability
            for pid in ("node/1", "node/2"):
                self.assertIsNotNone(get_crm_lead(pid))
                self.assertIsNotNone(get_business(pid))

            # ── Phase 4: ranking
            from analysis.opportunity_ranker import rank_all

            rankings = rank_all(20)
            self.assertEqual(len(rankings), 2)
            self.assertGreater(rankings[0][2].final_score, 0)

            # ── Phase 5: prepare outreach -> Pending Approval only
            import main

            main.cmd_prepare_outreach(argparse.Namespace(
                place_id="node/1", channel="email", followup=False))
            drafts = get_outreach_drafts()
            self.assertEqual(len(drafts), 1)
            first_draft_id = drafts[0]["id"]
            self.assertEqual(drafts[0]["status"], "Pending Approval")

            # ── Phase 6: approve -> mark-sent -> CRM Contacted -> log response
            main.cmd_approve(argparse.Namespace(draft_id=first_draft_id))
            self.assertEqual(get_outreach_drafts("Approved")[0]["id"], first_draft_id)

            main.cmd_mark_sent(argparse.Namespace(draft_id=first_draft_id))
            self.assertEqual(get_outreach_drafts("Sent")[0]["id"], first_draft_id)
            crm = get_crm_lead("node/1")
            self.assertEqual(crm["pipeline_status"], "Contacted")
            self.assertEqual(crm["last_contact_date"], date.today().isoformat())

            main.cmd_log_response(argparse.Namespace(
                draft_id=first_draft_id, text="We are very interested"))
            crm = get_crm_lead("node/1")
            self.assertEqual(crm["pipeline_status"], "Warm")

            # ── Phase 7: another sent draft, then backdate to trigger follow-up
            second_draft_id = save_outreach_draft(OutreachDraft(
                place_id="node/2", channel="email", personalization_hook="h",
                body="b", status="Pending Approval"))
            main.cmd_approve(argparse.Namespace(draft_id=second_draft_id))
            main.cmd_mark_sent(argparse.Namespace(draft_id=second_draft_id))
            with get_connection() as conn:
                conn.execute(
                    "UPDATE crm_leads SET last_contact_date=?, next_follow_up_date=? "
                    "WHERE place_id='node/2'",
                    (days_ago(10), days_ago(3)),
                )
            due = list_leads_due_for_followup()
            self.assertEqual([l["place_id"] for l in due], ["node/2"])

            main.cmd_prepare_outreach(argparse.Namespace(
                place_id="node/2", channel="email", followup=True))
            followup_drafts = get_outreach_drafts("Pending Approval")
            self.assertEqual(len(followup_drafts), 1)
            self.assertEqual(followup_drafts[0]["place_id"], "node/2")

            # ── Phase 8: insights + funnel
            stats = {s["category"]: s for s in category_conversion_stats()}
            row = stats["restaurant"]
            self.assertEqual(row["contacted"], 2)
            self.assertEqual(row["replied"], 1)

            metrics = get_funnel_metrics()
            self.assertEqual(metrics["businesses_found"], 2)
            self.assertEqual(metrics["proposals_generated"], 2)
            self.assertEqual(metrics["outreach_drafted"], 3)   # 2 first-contact + 1 follow-up
            self.assertEqual(metrics["outreach_sent"], 2)
            self.assertEqual(metrics["responses_logged"], 1)
            self.assertEqual(metrics["interested"], 1)


class _FakeResp:
    def __init__(self, text):
        self.text = text
        self.status_code = 200

    def raise_for_status(self):
        return None


if __name__ == "__main__":
    unittest.main()