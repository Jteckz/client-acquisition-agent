"""Phase 3 — Problem detection & solution recommendation (V1).

Covers analysis/problem_detector.py, analysis/solution_recommender.py,
analysis/lead_scorer.py and reports/report_builder.py. The LLM is replaced
with a fake; scoring stays deterministic.
"""
from __future__ import annotations

import unittest

from analysis.lead_scorer import score_lead
from analysis.problem_detector import detect_problems
from analysis.solution_recommender import recommend_solutions
from reports.report_builder import build_lead_report, render_report

from tests.helpers import (
    make_bundle,
    make_problems,
    make_social,
    make_solutions,
    make_website,
    patch_llm,
)


class ProblemDetectorTest(unittest.TestCase):
    def test_detect_problems_returns_llm_problems(self):
        with patch_llm([("Business: Test Cafe", {
            "problems": ["No website found", "No online ordering"],
            "reasoning": "Evidence supports both.",
        })]):
            analysis = detect_problems(make_bundle())
        self.assertEqual(analysis.problems, ["No website found", "No online ordering"])
        self.assertEqual(analysis.reasoning, "Evidence supports both.")

    def test_website_summary_includes_signals(self):
        bundle = make_bundle(
            website=make_website(
                has_website=True,
                reachable=True,
                is_mobile_friendly=True,
                has_ssl=True,
                signals_found=["online_menu"],
                signals_missing=["online_ordering"],
            )
        )
        with patch_llm([("Website findings", {})]) as fake:
            detect_problems(bundle)
            prompt = fake.generate_json_calls[0]
        self.assertIn("Features found: online_menu", prompt)
        self.assertIn("Features missing: online_ordering", prompt)


class SolutionRecommenderTest(unittest.TestCase):
    def test_recommendations_returned_for_problems(self):
        with patch_llm([("Problems:", {
            "solutions": ["Online ordering platform"],
            "potential_value": "High",
            "reasoning": "Strong fit.",
        })]):
            rec = recommend_solutions(
                make_bundle().business, make_problems("No website")
            )
        self.assertEqual(rec.solutions, ["Online ordering platform"])
        self.assertEqual(rec.potential_value, "High")

    def test_no_problems_short_circuits_without_llm(self):
        with patch_llm([]) as fake:
            rec = recommend_solutions(
                make_bundle().business, make_problems()
            )
            calls = list(fake.generate_json_calls)
        self.assertEqual(rec.solutions, [])
        self.assertEqual(calls, [])


class LeadScorerTest(unittest.TestCase):
    def test_no_website_no_social_scores_problem_points(self):
        bundle = make_bundle()  # no website, no social, phone+address set
        score, priority, reasons = score_lead(
            bundle, make_problems("No website"), make_solutions()
        )
        # no_website 25 + no_social 15 + established 10 + Medium 8 = 58
        self.assertEqual(score, 58)
        self.assertEqual(priority, "Medium")
        self.assertIn("No website found", reasons)

    def test_missing_features_add_ordering_and_booking_points(self):
        bundle = make_bundle(
            website=make_website(
                has_website=True,
                reachable=True,
                is_mobile_friendly=True,
                signals_found=["online_menu"],
                signals_missing=["online_ordering", "online_booking"],
            )
        )
        score, _, reasons = score_lead(
            bundle, make_problems(), make_solutions(potential_value="Low")
        )
        # mobile ok -> no penalty; ordering 15 + booking 10 + social 15 + est 10 = 50
        self.assertEqual(score, 50)
        self.assertIn("No online ordering", reasons)

    def test_priority_boundaries(self):
        from analysis.lead_scorer import _priority_for_score

        cases = [
            (100, "High"), (70, "High"), (69, "Medium"),
            (40, "Medium"), (39, "Low"), (0, "Low"),
        ]
        for value, expected in cases:
            self.assertEqual(_priority_for_score(value), expected, f"score={value}")

    def test_score_capped_at_100(self):
        bundle = make_bundle(
            website=make_website(
                has_website=True,
                is_mobile_friendly=False,
                signals_missing=["online_ordering", "online_booking"],
            ),
            social=make_social(platforms_found=["facebook"]),
        )
        score, _, _ = score_lead(
            bundle, make_problems(), make_solutions(potential_value="High")
        )
        self.assertLessEqual(score, 100)


class ReportBuilderTest(unittest.TestCase):
    def test_build_lead_report_runs_full_v1_chain(self):
        with patch_llm([
            ("Website findings:", {
                "problems": ["No website found"],
                "reasoning": "x",
            }),
            ("software consultant", {
                "solutions": ["Website builder"],
                "potential_value": "Medium",
                "reasoning": "y",
            }),
        ]):
            report = build_lead_report(make_bundle())
        self.assertEqual(report.business.name, "Test Cafe")
        self.assertEqual(report.problems, ["No website found"])
        self.assertEqual(report.solutions, ["Website builder"])
        self.assertEqual(report.lead_score, 58)
        self.assertEqual(report.priority, "Medium")

    def test_render_report_renders_business_name(self):
        with patch_llm([
            ("Website findings:", {"problems": [], "reasoning": ""}),
            ("software consultant", {"solutions": [], "potential_value": "Low"}),
        ]):
            report = build_lead_report(make_bundle())
        text = render_report(report)
        self.assertIn("Test Cafe", text)


if __name__ == "__main__":
    unittest.main()