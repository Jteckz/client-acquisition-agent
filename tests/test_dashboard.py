"""Phase 8 — Dashboard / funnel reporting (V3).

Funnel counts must match the underlying rows exactly, and the CSV export
must contain both the funnel section and the detail rows.
"""
from __future__ import annotations

import unittest

from discovery.models import OutreachDraft
from storage.db import (
    get_connection,
    get_dashboard_detail_rows,
    get_funnel_metrics,
    save_business,
    save_outreach_draft,
    save_response,
    update_crm_after_response,
)
from reports.dashboard import _format_budget, export_dashboard_csv

from tests.helpers import TempDBTestCase, make_business


class FunnelMetricsTest(TempDBTestCase):
    def test_metrics_match_seeded_rows(self):
        save_business(make_business(place_id="node/1", name="Cafe One"))
        save_business(make_business(place_id="node/2", name="Cafe Two"))

        # analyzed + qualified for node/1 only
        with get_connection() as conn:
            conn.execute(
                "INSERT INTO lead_reports (place_id, problems_json, lead_score, priority) "
                "VALUES ('node/1', '[]', 50, 'Medium')"
            )
            conn.execute(
                "INSERT INTO qualification_scores (place_id, total_score, priority) "
                "VALUES ('node/1', 70, 'High')"
            )
            conn.execute(
                "INSERT INTO proposals (place_id, package_name) VALUES ('node/1', 'Platform')"
            )

        # drafts: 1 pending, 1 approved, 1 sent -> drafted 3, approved 2, sent 1
        save_outreach_draft(OutreachDraft(
            place_id="node/1", channel="email", personalization_hook="h", body="b"))
        save_outreach_draft(OutreachDraft(
            place_id="node/1", channel="email", personalization_hook="h", body="b",
            status="Approved"))
        sent = save_outreach_draft(OutreachDraft(
            place_id="node/1", channel="email", personalization_hook="h", body="b",
            status="Sent"))
        # a Warm response on node/1
        save_response("node/1", sent, "Interested", "Warm Lead")
        # node/2 won (no outreach but converted via CRM)
        update_crm_after_response("node/2", "Converted")

        metrics = get_funnel_metrics()
        self.assertEqual(metrics["businesses_found"], 2)
        self.assertEqual(metrics["analyzed"], 1)
        self.assertEqual(metrics["qualified"], 1)
        self.assertEqual(metrics["proposals_generated"], 1)
        self.assertEqual(metrics["outreach_drafted"], 3)
        self.assertEqual(metrics["outreach_approved"], 2)
        self.assertEqual(metrics["outreach_sent"], 1)
        self.assertEqual(metrics["responses_logged"], 1)
        self.assertEqual(metrics["interested"], 1)  # Warm Lead counted
        self.assertEqual(metrics["clients_won"], 1)

    def test_empty_database_metrics_are_zero(self):
        metrics = get_funnel_metrics()
        for key in ("businesses_found", "analyzed", "qualified", "outreach_sent",
                    "responses_logged", "interested", "clients_won"):
            self.assertEqual(metrics[key], 0, key)

    def test_detail_rows_include_pipeline_and_rank(self):
        save_business(make_business(place_id="node/1", name="Cafe One"))
        with get_connection() as conn:
            conn.execute(
                "INSERT INTO qualification_scores (place_id, total_score, priority) "
                "VALUES ('node/1', 60, 'Medium')"
            )
            conn.execute(
                "INSERT INTO opportunity_rankings (place_id, final_score) VALUES ('node/1', 80)"
            )
            conn.execute(
                "INSERT INTO crm_leads (place_id, pipeline_status) VALUES ('node/1', 'New')"
            )
        rows = get_dashboard_detail_rows(10)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["rank_score"], 80)
        self.assertEqual(rows[0]["total_score"], 60)
        self.assertEqual(rows[0]["pipeline_status"], "New")


class DashboardExportTest(TempDBTestCase):
    def test_export_writes_funnel_and_detail_sections(self):
        import tempfile
        from pathlib import Path

        save_business(make_business(place_id="node/1", name="Cafe One"))
        with get_connection() as conn:
            conn.execute(
                "INSERT INTO qualification_scores (place_id, total_score, priority) "
                "VALUES ('node/1', 55, 'Medium')"
            )
            conn.execute(
                "INSERT INTO proposals (place_id, package_name, cost_min, cost_max) "
                "VALUES ('node/1', 'Platform', 100, 200)"
            )

        out = Path(tempfile.mkdtemp()) / "dash.csv"
        export_dashboard_csv(str(out), limit=50)
        text = out.read_text()
        self.assertIn("Section,Metric,Value", text)
        self.assertIn("Businesses Found", text)
        self.assertIn("Business,Category,Rank Score", text)
        self.assertIn("Cafe One", text)

    def test_format_budget_handles_none(self):
        self.assertEqual(_format_budget({"cost_min": None, "cost_max": None}), "-")
        self.assertEqual(_format_budget({"cost_min": 100, "cost_max": 200}), "$100–$200")


if __name__ == "__main__":
    unittest.main()