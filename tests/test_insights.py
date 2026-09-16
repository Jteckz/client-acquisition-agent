"""Phase 8 — Insights / knowledge base (V3): SQL aggregation + gating.

The knowledge base is plain counts over the CRM/outreach data, and it only
feeds recommendations once a category has >= MIN_SAMPLE_SIZE_FOR_INSIGHTS
contacted leads — small samples return empty context.
"""
from __future__ import annotations

import io
import unittest
from contextlib import redirect_stdout

from analysis.insights import (
    category_conversion_stats,
    insight_context_for_category,
    print_insights,
)
from config.settings import settings
from discovery.models import OutreachDraft
from storage.db import (
    get_connection,
    save_business,
    save_outreach_draft,
    save_response,
    update_crm_after_response,
)

from tests.helpers import TempDBTestCase, make_business


class InsightsTest(TempDBTestCase):
    def _seed_restaurant_leads(self):
        # biz1: contacted + replied (Warm)
        save_business(make_business(place_id="node/1", name="Cafe One"))
        save_outreach_draft(OutreachDraft(
            place_id="node/1", channel="email", personalization_hook="h",
            body="b", status="Sent",
        ))
        did1 = save_outreach_draft(OutreachDraft(
            place_id="node/1", channel="email", personalization_hook="h",
            body="b", status="Sent",
        ))
        save_response("node/1", did1, "Interested", "Warm Lead")

        # biz2: contacted + replied + Converted with a proposal package
        save_business(make_business(place_id="node/2", name="Cafe Two"))
        did2 = save_outreach_draft(OutreachDraft(
            place_id="node/2", channel="email", personalization_hook="h",
            body="b", status="Sent",
        ))
        save_response("node/2", did2, "Yes please", "Converted")
        update_crm_after_response("node/2", "Converted")  # -> pipeline Won
        with get_connection() as conn:
            conn.execute(
                "INSERT INTO proposals (place_id, package_name) VALUES (?, ?)",
                ("node/2", "Restaurant Digital Platform"),
            )

        # biz3: never contacted
        save_business(make_business(place_id="node/3", name="Cafe Three"))

    def test_category_conversion_stats_aggregates(self):
        self._seed_restaurant_leads()
        stats = {s["category"]: s for s in category_conversion_stats()}
        row = stats["restaurant"]
        self.assertEqual(row["total"], 3)
        self.assertEqual(row["contacted"], 2)
        self.assertEqual(row["replied"], 2)
        self.assertEqual(row["converted"], 1)
        self.assertEqual(row["conversion_rate"], 50)  # round(1/2 * 100)
        self.assertEqual(row["common_package"], "Restaurant Digital Platform")

    def test_context_empty_below_sample_size(self):
        self._seed_restaurant_leads()  # only 2 contacted, default min is 5
        self.assertEqual(insight_context_for_category("restaurant"), "")

    def test_context_present_at_or_above_sample_size(self):
        self._seed_restaurant_leads()
        settings.MIN_SAMPLE_SIZE_FOR_INSIGHTS = 2
        try:
            context = insight_context_for_category("restaurant")
        finally:
            settings.MIN_SAMPLE_SIZE_FOR_INSIGHTS = 5
        self.assertIn("Historical note", context)
        self.assertIn("Restaurant Digital Platform", context)

    def test_print_insights_renders_table(self):
        self._seed_restaurant_leads()
        buf = io.StringIO()
        with redirect_stdout(buf):
            print_insights()
        self.assertIn("restaurant", buf.getvalue())
        self.assertIn("Common converted package", buf.getvalue())


if __name__ == "__main__":
    unittest.main()