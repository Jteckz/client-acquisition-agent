"""Phase 4 — Qualification (V2): deterministic lead qualification scoring."""
from __future__ import annotations

import unittest

from analysis.lead_qualifier import qualify_lead

from tests.helpers import make_bundle, make_problems, make_social, make_website


class LeadQualifierTest(unittest.TestCase):
    def _active_bundle(self, **overrides):
        return make_bundle(
            website=make_website(
                has_website=True,
                reachable=True,
                is_mobile_friendly=True,
            ),
            social=make_social(platforms_found=["facebook"]),
            **overrides,
        )

    def test_strong_lead_scores_high(self):
        bundle = self._active_bundle()
        qual = qualify_lead(bundle, make_problems("No online ordering", "No booking"))
        # activity 20 + digital 15 + pay 15 + need 35 = 85
        self.assertEqual(qual.total_score, 85)
        self.assertEqual(qual.priority, "High")
        self.assertTrue(any(r.startswith("Active business") for r in qual.reasoning))
        self.assertIn("Strong digital presence", qual.reasoning)

    def test_ability_to_pay_high_value_category(self):
        from tests.helpers import make_business

        hotel = make_bundle(
            business=make_business(
                place_id="node/2", category="hotel", website="https://hotel.example"
            ),
            website=make_website(has_website=True, reachable=True, is_mobile_friendly=True),
            social=make_social(platforms_found=["facebook"]),
        )
        qual = qualify_lead(hotel, make_problems("No booking"))
        self.assertEqual(qual.ability_to_pay_score, 30)
        self.assertIn("Appears able to invest in solutions", qual.reasoning)

    def test_phone_only_medium_pay(self):
        bundle = make_bundle(
            website=make_website(has_website=False, reachable=False),
            social=make_social(),
        )
        qual = qualify_lead(bundle, make_problems())
        self.assertEqual(qual.ability_to_pay_score, 15)  # phone present -> medium

    def test_no_contact_info_low_pay(self):
        from tests.helpers import make_business

        bundle = make_bundle(
            business=make_business(phone=None, website=None),
            website=make_website(has_website=False, reachable=False),
            social=make_social(),
        )
        qual = qualify_lead(bundle, make_problems())
        self.assertEqual(qual.ability_to_pay_score, 5)

    def test_score_clamped_below_zero(self):
        bundle = make_bundle(
            website=make_website(has_website=False, reachable=False),
            social=make_social(),
        )
        qual = qualify_lead(bundle, make_problems())
        self.assertGreaterEqual(qual.total_score, 0)
        self.assertIn(qual.priority, ("Low", "Medium"))


if __name__ == "__main__":
    unittest.main()