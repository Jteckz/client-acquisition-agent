"""Settings fallback + phased-rollout acceptance tests.

Covers:
  - Legacy OLLAMA_MODEL-only deployments still resolve both roles (§12.2)
  - REASONING_MODEL_ENABLED=false runs everything on the worker model (§12.3)
  - Groq role mapping parity
"""
from __future__ import annotations

import os
import unittest
from unittest import mock

import llm.client
from config.settings import Settings, _first_set_env, settings
from llm.client import _clients, _effective_role, get_llm_client


class EnvResolutionTest(unittest.TestCase):
    def test_role_var_wins_over_legacy(self):
        with mock.patch.dict(os.environ, {
            "OLLAMA_WORKER_MODEL": "qwen2.5:3b-instruct",
            "OLLAMA_MODEL": "legacy",
        }):
            self.assertEqual(
                _first_set_env("OLLAMA_WORKER_MODEL", "OLLAMA_MODEL", default="d"),
                "qwen2.5:3b-instruct",
            )

    def test_legacy_model_used_when_role_vars_unset(self):
        with mock.patch.dict(os.environ, {"OLLAMA_MODEL": "legacy"}, clear=True):
            self.assertEqual(
                _first_set_env("OLLAMA_WORKER_MODEL", "OLLAMA_MODEL", default="d"),
                "legacy",
            )
            self.assertEqual(
                _first_set_env("OLLAMA_REASONING_MODEL", "OLLAMA_MODEL", default="d"),
                "legacy",
            )

    def test_default_applied_when_nothing_set(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            self.assertEqual(
                _first_set_env("OLLAMA_WORKER_MODEL", "OLLAMA_MODEL", default="qwen2.5:3b-instruct"),
                "qwen2.5:3b-instruct",
            )

    def test_empty_role_var_falls_back_to_legacy(self):
        with mock.patch.dict(os.environ, {"OLLAMA_MODEL": "legacy", "OLLAMA_WORKER_MODEL": ""}):
            self.assertEqual(
                _first_set_env("OLLAMA_WORKER_MODEL", "OLLAMA_MODEL", default="d"),
                "legacy",
            )


class LegacyBackwardCompatTest(unittest.TestCase):
    """§12.2: only legacy OLLAMA_MODEL set -> both roles resolve to it."""

    def setUp(self):
        _clients.clear()

    def test_factory_resolves_both_roles_to_legacy_model(self):
        with mock.patch.object(settings, "OLLAMA_WORKER_MODEL", "legacy-model"), \
             mock.patch.object(settings, "OLLAMA_REASONING_MODEL", "legacy-model"), \
             mock.patch.object(settings, "LLM_PROVIDER", "ollama"), \
             mock.patch("llm.client.OllamaClient") as OC:
            get_llm_client("worker")
            get_llm_client("reasoning")
        models = [c.kwargs["model"] for c in OC.call_args_list]
        self.assertEqual(models, ["legacy-model", "legacy-model"])

    def test_model_for_role_returns_legacy_for_both(self):
        s = Settings()
        with mock.patch.object(s, "OLLAMA_WORKER_MODEL", "legacy-model"), \
             mock.patch.object(s, "OLLAMA_REASONING_MODEL", "legacy-model"):
            self.assertEqual(s.model_for_role("worker"), "legacy-model")
            self.assertEqual(s.model_for_role("reasoning"), "legacy-model")


class GroqParityTest(unittest.TestCase):
    def test_groq_role_mapping_uses_role_models(self):
        s = Settings()
        with mock.patch.object(s, "LLM_PROVIDER", "groq"), \
             mock.patch.object(s, "GROQ_WORKER_MODEL", "worker-hosted"), \
             mock.patch.object(s, "GROQ_REASONING_MODEL", "reasoning-hosted"):
            self.assertEqual(s.model_for_role("worker"), "worker-hosted")
            self.assertEqual(s.model_for_role("reasoning"), "reasoning-hosted")

    def test_factory_constructs_groq_with_role_model(self):
        _clients.clear()
        with mock.patch.object(settings, "LLM_PROVIDER", "groq"), \
             mock.patch.object(settings, "GROQ_WORKER_MODEL", "worker-hosted"), \
             mock.patch.object(settings, "GROQ_REASONING_MODEL", "reasoning-hosted"), \
             mock.patch.object(settings, "GROQ_API_KEY", "k"), \
             mock.patch("llm.client.GroqClient") as GC:
            get_llm_client("worker")
            get_llm_client("reasoning")
        models = [c.kwargs["model"] for c in GC.call_args_list]
        self.assertEqual(models, ["worker-hosted", "reasoning-hosted"])


class PhasedRolloutTest(unittest.TestCase):
    """§12.3: REASONING_MODEL_ENABLED=false -> worker model only."""

    def setUp(self):
        _clients.clear()
        llm.client._worker_only_warned = False

    def test_reasoning_requests_fall_back_to_worker_client(self):
        with mock.patch.object(settings, "REASONING_MODEL_ENABLED", False), \
             mock.patch.object(settings, "OLLAMA_WORKER_MODEL", "worker-model"), \
             mock.patch.object(settings, "OLLAMA_REASONING_MODEL", "reasoning-model"), \
             mock.patch("llm.client.OllamaClient") as OC:
            worker = get_llm_client("worker")
            reasoning = get_llm_client("reasoning")

        # identical effective role -> one shared client, never the reasoning model
        self.assertIs(worker, reasoning)
        OC.assert_called_once()
        self.assertEqual(OC.call_args.kwargs["model"], "worker-model")

    def test_effective_role_maps_reasoning_to_worker(self):
        with mock.patch.object(settings, "REASONING_MODEL_ENABLED", False):
            self.assertEqual(_effective_role("reasoning"), "worker")
            self.assertEqual(_effective_role("worker"), "worker")

    def test_enabled_mode_keeps_two_separate_clients(self):
        with mock.patch.object(settings, "REASONING_MODEL_ENABLED", True), \
             mock.patch.object(settings, "OLLAMA_WORKER_MODEL", "worker-model"), \
             mock.patch.object(settings, "OLLAMA_REASONING_MODEL", "reasoning-model"), \
             mock.patch("llm.client.OllamaClient") as OC:
            get_llm_client("worker")
            get_llm_client("reasoning")
        models = [c.kwargs["model"] for c in OC.call_args_list]
        self.assertEqual(models, ["worker-model", "reasoning-model"])

    def test_worker_only_warning_logged_once(self):
        with mock.patch.object(settings, "REASONING_MODEL_ENABLED", False), \
             mock.patch.object(settings, "OLLAMA_WORKER_MODEL", "worker-model"), \
             mock.patch("llm.client.OllamaClient"), \
             self.assertLogs("llm.client", level="WARNING") as logs:
            get_llm_client("reasoning")
            get_llm_client("reasoning")
        warnings = [l for l in logs.output if "worker-only" in l]
        self.assertEqual(len(warnings), 1)


if __name__ == "__main__":
    unittest.main()
