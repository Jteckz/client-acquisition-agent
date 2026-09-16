"""Phase 5 — Outreach drafting (V3): personalization hook + channel drafts.

The key rule under test: every draft is created with status
"Pending Approval" and nothing is ever sent. The LLM is faked, including
its failure modes (empty body, generic hooks) that trigger the retry /
fallback logic.
"""
from __future__ import annotations

import unittest

from analysis.outreach_drafter import draft_outreach
from analysis.outreach_preparer import prepare_hook

from tests.helpers import make_bundle, make_problems, patch_llm


class OutreachPreparerTest(unittest.TestCase):
    def test_hook_referencing_findings_accepted_on_first_try(self):
        problems = make_problems("No website found")
        with patch_llm([
            ("Problems found:", {"hook": "Noticing Test Cafe has no website"}),
        ]) as fake:
            hook = prepare_hook("Test Cafe", "restaurant", problems, make_bundle())
            calls = list(fake.generate_json_calls)
        self.assertEqual(hook, "Noticing Test Cafe has no website")
        self.assertEqual(len(calls), 1)

    def test_generic_hook_retried_then_fallback(self):
        problems = make_problems("No website found")

        def generic(prompt, n):
            return {"hook": "Hello there"}

        with patch_llm([("Problems found:", generic)]) as fake:
            hook = prepare_hook("Test Cafe", "restaurant", problems, make_bundle())
            calls = list(fake.generate_json_calls)
        self.assertEqual(len(calls), 2)
        self.assertEqual(hook, "Noticing Test Cafe could use help with no website found.")

    def test_no_problems_falls_back_to_generic_growth_line(self):
        with patch_llm([]):
            hook = prepare_hook("Test Cafe", "restaurant", make_problems(), make_bundle())
        self.assertEqual(hook, "Seeing ways Test Cafe could grow its digital presence.")


class OutreachDrafterTest(unittest.TestCase):
    HOOK = "We noticed Test Cafe has no website."

    def test_email_draft_is_pending_approval_with_subject(self):
        with patch_llm([("Personalization hook", {
            "subject": "A website for Test Cafe",
            "body": "Hi there, open to a short call?",
        })]):
            draft = draft_outreach("node/1", "email", "Test Cafe", self.HOOK)
        self.assertEqual(draft.status, "Pending Approval")
        self.assertEqual(draft.channel, "email")
        self.assertEqual(draft.subject, "A website for Test Cafe")
        self.assertEqual(draft.personalization_hook, self.HOOK)

    def test_linkedin_draft_has_no_subject(self):
        with patch_llm([("Personalization hook", {"body": "Short LinkedIn msg"})]):
            draft = draft_outreach("node/1", "linkedin", "Test Cafe", self.HOOK)
        self.assertIsNone(draft.subject)
        self.assertEqual(draft.status, "Pending Approval")

    def test_unsupported_channel_raises(self):
        with self.assertRaises(ValueError):
            draft_outreach("node/1", "fax", "Test Cafe", self.HOOK)

    def test_empty_body_retried_once(self):
        def flaky(prompt, n):
            return {} if n == 0 else {"body": "Second attempt body"}

        with patch_llm([("Personalization hook", flaky)]):
            draft = draft_outreach("node/1", "email", "Test Cafe", self.HOOK)
        self.assertEqual(draft.body, "Second attempt body")

    def test_repeated_empty_body_falls_back_to_placeholder(self):
        with patch_llm([("Personalization hook", {})]):
            draft = draft_outreach("node/1", "whatsapp", "Test Cafe", self.HOOK)
        self.assertEqual(draft.body, "[Draft failed to generate — please rewrite manually]")

    def test_followup_context_references_original_body(self):
        original = "Original first-contact email body."
        with patch_llm([("Personalization hook", {"body": "Follow-up body"})]) as fake:
            draft = draft_outreach(
                "node/1", "email", "Test Cafe", self.HOOK, original_body=original
            )
            prompt = fake.generate_json_calls[0]
        self.assertEqual(draft.status, "Pending Approval")
        self.assertIn(original, prompt)  # follow-up prompt references prior message


if __name__ == "__main__":
    unittest.main()