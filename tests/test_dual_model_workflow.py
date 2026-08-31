"""Additional dual-model workflow validation.

Fills gaps left by the phase-specific suites:
- The Solution Library's package_name is authoritative when a template exists
  (regression guard: the reasoning model must not rename a template package).
- Per-role clients are cached separately and bound to the right model in
  dual-model mode.
- JSON extraction from small-model output (fences, preamble, trailing text,
  garbage) degrades gracefully.
- model-status formatting of raw Ollama sizes.
- prepare_hook degrades to a safe, honest fallback when no problems exist.
"""
from __future__ import annotations

import unittest
from unittest import mock

from analysis.outreach_preparer import prepare_hook
from analysis.solution_designer import design_solution
from config.settings import settings

from tests.helpers import (
    TempDBTestCase,
    make_bundle,
    make_problems,
    patch_llm,
)


class SolutionLibraryAuthorityTest(unittest.TestCase):
    """package_name must come from the template, never trusted from the LLM."""

    def test_template_name_wins_over_llm_invented_name(self):
        with patch_llm([("Available template", {
            "package_name": "Completely Different Name",
            "features": ["Online Booking", "WhatsApp Booking"],
            "reasoning": "chosen",
        })]):
            blueprint, template = design_solution("hotel", make_problems("No booking"))
        self.assertIsNotNone(template)
        self.assertEqual(blueprint.package_name, "Hotel Digital Presence Platform")
        self.assertEqual(blueprint.features, ["Online Booking", "WhatsApp Booking"])

    def test_template_name_kept_when_llm_returns_template_name(self):
        with patch_llm([("Available template", {
            "package_name": "Restaurant Digital Platform",
            "features": ["Website"],
            "reasoning": "",
        })]):
            blueprint, template = design_solution("restaurant", make_problems("No site"))
        self.assertEqual(blueprint.package_name, "Restaurant Digital Platform")

    def test_no_template_keeps_llm_chosen_name(self):
        with patch_llm([("No template available", {
            "package_name": "Zorb Arena Suite",
            "features": ["Website"],
            "reasoning": "",
        })]):
            blueprint, template = design_solution("zorb-laser-arena", make_problems("No site"))
        self.assertIsNone(template)
        self.assertEqual(blueprint.package_name, "Zorb Arena Suite")

    def test_no_template_empty_llm_defaults_to_custom_solution(self):
        with patch_llm([]):
            blueprint, template = design_solution("gym", make_problems("No site"))
        self.assertIsNone(template)
        self.assertEqual(blueprint.package_name, "Custom Solution")


class RoleClientCacheTest(unittest.TestCase):
    def test_reasoning_and_worker_use_distinct_cached_clients(self):
        import llm.client as llm_client

        saved = dict(llm_client._clients)
        try:
            llm_client._clients.clear()
            with mock.patch.object(settings, "REASONING_MODEL_ENABLED", True):
                worker = llm_client.get_llm_client("worker")
                reasoning = llm_client.get_llm_client("reasoning")
            self.assertIsNot(worker, reasoning)
            self.assertEqual(worker.model, settings.OLLAMA_WORKER_MODEL)
            self.assertEqual(reasoning.model, settings.OLLAMA_REASONING_MODEL)
            # second call reuses cache
            self.assertIs(llm_client.get_llm_client("worker"), worker)
            self.assertIs(llm_client.get_llm_client("reasoning"), reasoning)
            self.assertEqual(set(llm_client._clients), {"worker", "reasoning"})
        finally:
            llm_client._clients.clear()
            llm_client._clients.update(saved)

    def test_worker_only_mode_never_instantiates_reasoning_copy(self):
        import llm.client as llm_client

        saved = dict(llm_client._clients)
        try:
            llm_client._clients.clear()
            with mock.patch.object(settings, "REASONING_MODEL_ENABLED", False):
                client = llm_client.get_llm_client("reasoning")
            self.assertEqual(client.model, settings.OLLAMA_WORKER_MODEL)
            self.assertEqual(set(llm_client._clients), {"worker"})
        finally:
            llm_client._clients.clear()
            llm_client._clients.update(saved)


class JsonExtractionTest(unittest.TestCase):
    def _extract(self, raw: str) -> dict:
        from llm.client import _extract_json

        return _extract_json(raw)

    def test_plain_json(self):
        self.assertEqual(self._extract('{"a": 1}'), {"a": 1})

    def test_fenced_json(self):
        raw = '```json\n{"problems": ["no site"]}\n```'
        self.assertEqual(self._extract(raw), {"problems": ["no site"]})

    def test_preamble_before_json(self):
        raw = 'Here is the analysis: {"status": "Warm Lead"} thanks!'
        self.assertEqual(self._extract(raw), {"status": "Warm Lead"})

    def test_nested_braces_greedy_block(self):
        raw = 'prefix {"a": {"b": [1, 2]}} suffix'
        self.assertEqual(self._extract(raw), {"a": {"b": [1, 2]}})

    def test_garbage_returns_empty_dict(self):
        self.assertEqual(self._extract("I am sorry, I cannot do that."), {})


class ModelStatusFormatTest(unittest.TestCase):
    def test_human_bytes(self):
        from main import _human_bytes

        self.assertEqual(_human_bytes(0), "-")
        self.assertEqual(_human_bytes(512), "512B")
        self.assertEqual(_human_bytes(2048), "2KB")
        self.assertEqual(_human_bytes(5 * 1024 * 1024), "5MB")
        self.assertEqual(_human_bytes(7_300_000_000), "6.8GB")

    def test_human_bytes_never_crashes_on_empty_models_list(self):
        # exercises the CLI path with an empty models list returned by /api/ps
        import main

        with mock.patch("requests.get") as get:
            get.return_value.json.return_value = {"models": []}
            try:
                main.cmd_model_status(mock.Mock())
            except SystemExit as exc:
                # "No models currently resident" path exits cleanly with code 0
                self.assertEqual(exc.code, 0)

    def test_human_bytes_handles_ollama_ps_fields(self):
        import main

        with mock.patch("requests.get") as get:
            get.return_value.json.return_value = {
                "models": [{
                    "name": "qwen2.5:7b", "size": 5_100_000_000,
                    "size_vram": 5_100_000_000, "expires_at": "soon",
                }]
            }
            main.cmd_model_status(mock.Mock())  # must not raise


class PrepareHookFallbackTest(unittest.TestCase):
    def test_no_problems_yields_honest_fallback(self):
        problems = make_problems()
        with patch_llm([("Evidence gathered:", {"hook": "generic fluff"})]):
            hook = prepare_hook("Cafe", "restaurant", problems, make_bundle())
        self.assertIn("Cafe", hook)
        self.assertIn("grow", hook)

    def test_problems_present_yields_problem_referencing_fallback(self):
        problems = make_problems("No online ordering available")
        with patch_llm([("Evidence gathered:", {"hook": "completely unrelated sentence"})]):
            hook = prepare_hook("Cafe", "restaurant", problems, make_bundle())
        self.assertIn("online ordering", hook.lower())


class SolutionDesignIntermodelFeedTest(TempDBTestCase):
    def test_insight_context_only_added_above_sample_threshold(self):
        # solution designer must not crash when the knowledge base is empty
        from analysis.solution_designer import _insight_context

        self.assertEqual(_insight_context("restaurant"), "")


if __name__ == "__main__":
    unittest.main()