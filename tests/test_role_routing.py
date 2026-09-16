"""Acceptance tests for the dual-model role routing (V3 efficiency retrofit).

Every module calls the real `llm.client.get_llm_client(role=...)`, which
reads its per-role `_clients` cache. By swapping that cache for a recording
dict, each phase's requested role is captured through the real factory
path, per the phase->model table. Also covers the follow-up escalation rule,
the presence-summarizer feed into problem detection, and that rule-based
phases never touch the LLM.
"""
from __future__ import annotations

import unittest
from unittest import mock

from analysis.cost_estimator import estimate_cost
from analysis.followup_agent import draft_followup
from analysis.lead_qualifier import qualify_lead
from analysis.opportunity_ranker import rank_opportunity
from analysis.outreach_drafter import draft_outreach
from analysis.outreach_preparer import prepare_hook
from analysis.problem_detector import detect_problems
from analysis.response_classifier import classify_response
from analysis.solution_designer import design_solution
from analysis.solution_recommender import recommend_solutions
from analysis.tech_recommender import recommend_tech_stack
from config.settings import settings
from discovery.models import SolutionBlueprint
from reports.proposal_builder import generate_proposal
from research.presence_summarizer import summarize_presence

from tests.helpers import (
    FakeLLMClient,
    TempDBTestCase,
    make_bundle,
    make_qualification,
    make_reachability,
    make_problems,
    make_social,
    make_website,
    patch_llm,
)


def make_blueprint(name="Restaurant Digital Platform", features=None) -> SolutionBlueprint:
    return SolutionBlueprint(
        package_name=name,
        features=features or ["Website", "Digital Menu"],
        reasoning="fixture",
    )


class RecordingClients(dict):
    """dict that records which effective-role key was requested."""

    def __init__(self, fake):
        super().__init__({"worker": fake, "reasoning": fake})
        self.roles: list[str] = []

    def __getitem__(self, key):
        self.roles.append(key)
        return dict.__getitem__(self, key)


def capture_roles(fn, *args, **kwargs):
    """Run `fn` with a recording LLM cache; return the requested roles."""
    recording = RecordingClients(FakeLLMClient())
    with mock.patch("llm.client._clients", recording), \
         mock.patch.object(settings, "REASONING_MODEL_ENABLED", True):
        fn(*args, **kwargs)
    return list(recording.roles)


class ReasoningTierRoutingTest(unittest.TestCase):
    def test_problem_detection_requests_reasoning(self):
        self.assertEqual(
            capture_roles(detect_problems, make_bundle()), ["reasoning"]
        )

    def test_solution_recommendation_requests_reasoning(self):
        self.assertEqual(
            capture_roles(recommend_solutions, make_bundle().business, make_problems("No website")),
            ["reasoning"],
        )

    def test_solution_design_requests_reasoning(self):
        self.assertEqual(
            capture_roles(design_solution, "restaurant", make_problems("No website")),
            ["reasoning"],
        )

    def test_tech_stack_requests_reasoning(self):
        self.assertEqual(
            capture_roles(recommend_tech_stack, "gym", make_blueprint()),
            ["reasoning"],
        )

    def test_proposal_generation_requests_reasoning_for_exec_summary(self):
        qualified = make_bundle(
            website=make_website(has_website=True, reachable=True, is_mobile_friendly=True),
            social=make_social(platforms_found=["facebook"]),
        )
        roles = capture_roles(generate_proposal, qualified, make_problems("No website"))
        # design_solution (reasoning) + complexity (worker) + executive summary (reasoning)
        self.assertIn("reasoning", roles)
        self.assertIn("worker", roles)

    def test_prepare_hook_requests_reasoning(self):
        self.assertEqual(
            capture_roles(prepare_hook, "Cafe", "restaurant", make_problems("No website"), make_bundle()),
            ["reasoning"],
        )

    def test_first_contact_draft_requests_reasoning(self):
        self.assertEqual(
            capture_roles(draft_outreach, "node/1", "email", "Cafe", "hook"),
            ["reasoning"],
        )


class WorkerTierRoutingTest(unittest.TestCase):
    def test_presence_summarizer_requests_worker(self):
        self.assertEqual(
            capture_roles(summarize_presence, make_bundle()), ["worker"]
        )

    def test_cost_complexity_requests_worker(self):
        self.assertEqual(
            capture_roles(estimate_cost, make_blueprint(), None), ["worker"]
        )

    def test_response_classification_requests_worker(self):
        self.assertEqual(
            capture_roles(classify_response, "We are interested"), ["worker"]
        )


class FollowupEscalationTest(TempDBTestCase):
    def _seed_business_with_score(self, place_id, score):
        from storage.db import save_business, save_outreach_draft, save_qualification_score
        from discovery.models import OutreachDraft
        from tests.helpers import make_business

        save_business(make_business(place_id=place_id, name="Cafe"))
        save_qualification_score(place_id, make_qualification(total_score=score))
        save_outreach_draft(OutreachDraft(
            place_id=place_id, channel="email", personalization_hook="h",
            body="original", status="Sent",
        ))

    def test_low_score_followup_uses_worker(self):
        self._seed_business_with_score("node/1", 50)
        with mock.patch("analysis.followup_agent.draft_outreach") as drafter:
            draft_followup("node/1", "email")
        self.assertEqual(drafter.call_args.kwargs["role"], "worker")

    def test_high_score_followup_escalates_to_reasoning(self):
        self._seed_business_with_score("node/1", 95)
        with mock.patch("analysis.followup_agent.draft_outreach") as drafter:
            draft_followup("node/1", "email")
        self.assertEqual(drafter.call_args.kwargs["role"], "reasoning")

    def test_no_stored_score_defaults_to_worker(self):
        from storage.db import save_business, save_outreach_draft
        from discovery.models import OutreachDraft
        from tests.helpers import make_business

        save_business(make_business(place_id="node/9", name="Cafe"))
        save_outreach_draft(OutreachDraft(
            place_id="node/9", channel="email", personalization_hook="h",
            body="original", status="Sent",
        ))
        with mock.patch("analysis.followup_agent.draft_outreach") as drafter:
            draft_followup("node/9", "email")
        self.assertEqual(drafter.call_args.kwargs["role"], "worker")

    def test_escalation_boundary_is_strictly_greater(self):
        self._seed_business_with_score("node/1", 90)
        with mock.patch("analysis.followup_agent.draft_outreach") as drafter:
            draft_followup("node/1", "email")
        self.assertEqual(drafter.call_args.kwargs["role"], "worker")


class PresenceSummaryFeedTest(unittest.TestCase):
    def test_presence_summary_feeds_into_problem_detection(self):
        with patch_llm([
            ("Summarize this business's online presence", "Cafe has a reachable website."),
            ("Website findings:", {
                "problems": ["No online ordering"], "reasoning": "evidence",
            }),
        ]) as fake:
            from reports.report_builder import build_lead_report

            build_lead_report(make_bundle())
        # presence summary uses generate(); problem detection uses generate_json()
        self.assertTrue(any("Summarize this business's online presence" in c for c in fake.generate_calls))
        # the worker's summary text is fed into the reasoning model's prompt
        self.assertIn("Cafe has a reachable website.", fake.generate_json_calls[0])

    def test_detect_problems_without_summary_uses_placeholder(self):
        with patch_llm([("Website findings:", {"problems": [], "reasoning": ""})]) as fake:
            detect_problems(make_bundle())
        self.assertIn("No presence summary provided.", fake.generate_json_calls[0])


class RuleBasedPhasesNeverCallLLMTest(TempDBTestCase):
    def test_qualification_ranking_insights_dashboard_have_zero_llm_calls(self):
        blocked = mock.Mock(side_effect=AssertionError("rule-based phase must not call the LLM"))
        with mock.patch("llm.client.get_llm_client", blocked):
            qualify_lead(make_bundle(), make_problems("No website"))
            rank_opportunity(make_qualification(), make_reachability())

            from analysis.insights import category_conversion_stats
            from reports.dashboard import export_dashboard_csv

            self.assertEqual(category_conversion_stats(), [])
            export_dashboard_csv("nope.csv", 10)

        blocked.assert_not_called()


if __name__ == "__main__":
    unittest.main()
