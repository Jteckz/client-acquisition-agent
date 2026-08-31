"""Phase 4 — Proposal generation (V2): qualification gate + PDF output.

generate_proposal must refuse leads below MIN_QUALIFICATION_SCORE_FOR_PROPOSAL
and, for qualified leads, produce a complete ProposalDocument with a PDF
written to disk. The weasyprint backend is stubbed so the test runs without
rendering a real PDF.
"""
from __future__ import annotations

import unittest
from pathlib import Path
from unittest import mock

from config.settings import settings
from reports import proposal_builder

from tests.helpers import (
    TempDBTestCase,
    make_bundle,
    make_problems,
    make_social,
    make_website,
    patch_llm,
)


class FakeHTML:
    def __init__(self, string=None, *args, **kwargs):
        self.string = string

    def write_pdf(self, path):
        with open(path, "w") as f:
            f.write(self.string or "")


def _qualified_bundle():
    return make_bundle(
        website=make_website(
            has_website=True, reachable=True, is_mobile_friendly=True,
        ),
        social=make_social(platforms_found=["facebook"]),
    )


def _llm_responses():
    return [
        ("Available template", {
            "package_name": "Restaurant Digital Platform",
            "features": ["Website", "Digital Menu", "Online Ordering", "WhatsApp Integration"],
            "reasoning": "",
        }),
        ("Number of features", {"complexity": "Medium", "reasoning": ""}),
    ]


class ProposalBuilderTest(TempDBTestCase):
    def setUp(self):
        super().setUp()
        self._orig_threshold = settings.MIN_QUALIFICATION_SCORE_FOR_PROPOSAL

    def tearDown(self):
        settings.MIN_QUALIFICATION_SCORE_FOR_PROPOSAL = self._orig_threshold
        super().tearDown()

    def test_lead_below_threshold_skipped(self):
        settings.MIN_QUALIFICATION_SCORE_FOR_PROPOSAL = 99
        weak = make_bundle()  # no website, no social -> score clamps to 0
        with patch_llm(_llm_responses()), mock.patch(
            "reports.proposal_builder.HTML", FakeHTML
        ):
            doc = proposal_builder.generate_proposal(
                weak, make_problems("No website")
            )
        self.assertIsNone(doc)

    def test_qualified_lead_produces_complete_proposal(self):
        settings.MIN_QUALIFICATION_SCORE_FOR_PROPOSAL = 0
        with patch_llm(_llm_responses()), mock.patch(
            "reports.proposal_builder.HTML", FakeHTML
        ):
            doc = proposal_builder.generate_proposal(
                _qualified_bundle(),
                make_problems("No online ordering", "No booking"),
            )
        self.assertIsNotNone(doc)
        self.assertEqual(doc.status, "Ready for Outreach")
        self.assertEqual(doc.business_name, "Test Cafe")
        self.assertEqual(doc.identified_challenges, ["No online ordering", "No booking"])
        self.assertEqual(doc.proposed_solution.package_name, "Restaurant Digital Platform")
        # template default stack used without an LLM call
        self.assertEqual(doc.tech_stack.frontend, "React")
        # template base cost [1500, 2500], Medium multiplier 1.0, no extra features
        self.assertEqual(doc.cost_estimate.estimated_cost_min, 1500)
        self.assertEqual(doc.cost_estimate.estimated_cost_max, 2500)
        self.assertEqual(doc.cost_estimate.estimated_weeks_min, 3)
        # benefits derived deterministically from features + challenges
        self.assertTrue(any(b.endswith("online ordering") for b in doc.expected_benefits))
        self.assertTrue(any(b.startswith("Addresses key challenge") for b in doc.expected_benefits))

    def test_pdf_written_to_output_dir(self):
        settings.MIN_QUALIFICATION_SCORE_FOR_PROPOSAL = 0
        with patch_llm(_llm_responses()), mock.patch(
            "reports.proposal_builder.HTML", FakeHTML
        ):
            doc = proposal_builder.generate_proposal(
                _qualified_bundle(), make_problems("No booking")
            )
        self.assertIsNotNone(doc.pdf_path)
        self.assertTrue(Path(doc.pdf_path).exists())
        self.assertIn("test_cafe.pdf", doc.pdf_path)

    def test_render_html_contains_key_fields(self):
        from discovery.models import (
            CostEstimate,
            ProposalDocument,
            SolutionBlueprint,
            TechStack,
        )

        doc = ProposalDocument(
            business_name="Test Cafe",
            executive_summary="Summary.",
            identified_challenges=["No website"],
            proposed_solution=SolutionBlueprint(
                package_name="Restaurant Digital Platform", features=["Website"], reasoning=""
            ),
            tech_stack=TechStack(
                frontend="React", backend="FastAPI", database="PostgreSQL", hosting="DigitalOcean"
            ),
            cost_estimate=CostEstimate(
                complexity="Medium", estimated_cost_min=1000, estimated_cost_max=2000,
                estimated_weeks_min=3, estimated_weeks_max=5,
            ),
            expected_benefits=["Reach more customers"],
        )
        from tests.helpers import make_business

        html = proposal_builder._render_html(doc, make_business())
        self.assertIn("Test Cafe", html)
        self.assertIn("Restaurant Digital Platform", html)
        self.assertIn("1,000", html)  # _comma filter applied


if __name__ == "__main__":
    unittest.main()