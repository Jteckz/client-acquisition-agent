"""Shared test infrastructure for the client acquisition agent.

The suite is organized around the eight phases described in the README
("Phases of the agent's work"). This module provides:

- FakeLLMClient + patch_llm(): deterministic stand-in for the LLM. Locating
  the response by a substring match on the prompt keeps every call offline
  and repeatable. A callable value lets a test vary the reply per attempt
  (used for the retry logic in the outreach drafter).
- TempDBTestCase: points settings.DATABASE_PATH / PROPOSALS_OUTPUT_DIR at a
  throwaway temp directory for the duration of a test, so the automation
  never touches the real data/leads.db.
- Fixture builders for ResearchBundle / QualificationScore / etc.

All network and LLM activity in the unit tests is substituted by these
fakes so the whole suite runs offline and deterministically.
"""
from __future__ import annotations

import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Callable
from unittest import mock

from config.settings import settings
from discovery.models import (
    Business,
    ProblemAnalysis,
    QualificationScore,
    ReachabilityInfo,
    ResearchBundle,
    ReviewFindings,
    SocialFindings,
    SolutionRecommendation,
    WebsiteFindings,
)
from storage.db import init_db


class FakeLLMClient:
    """Deterministic fake LLM. `responses` is an ordered list of
    (substring, value) pairs; the first whose substring appears in the prompt
    wins. `value` may be a dict (for generate_json), a str (for generate),
    or a callable `(prompt, call_index) -> value`.
    """

    def __init__(self, responses: list[tuple[str, Any]] | None = None):
        self.responses = responses or []
        self.generate_json_calls: list[str] = []
        self.generate_calls: list[str] = []

    def _match(self, prompt: str, index: int) -> Any:
        for key, value in self.responses:
            if key in prompt:
                if callable(value):
                    return value(prompt, index)
                return value
        return {}

    def generate_json(self, prompt: str, system: str | None = None) -> dict:
        self.generate_json_calls.append(prompt)
        value = self._match(prompt, len(self.generate_json_calls) - 1)
        return value if isinstance(value, dict) else {"__value": value}

    def generate(self, prompt: str, system: str | None = None) -> str:
        self.generate_calls.append(prompt)
        value = self._match(prompt, len(self.generate_calls) - 1)
        return value if isinstance(value, str) else "Fake summary."


def patch_llm(responses: list[tuple[str, Any]] | None = None):
    """Context manager substituting the LLM with a FakeLLMClient.

    Many modules hold their own `from llm.client import get_llm_client`
    reference, so patching the function name is not enough. Instead we patch
    the module-level `_clients` role cache — the real `get_llm_client()`
    reads it on every role, so every call site gets the same fake. Yields the
    fake so tests can inspect prompts.
    """
    from contextlib import contextmanager

    @contextmanager
    def _patch():
        fake = FakeLLMClient(responses)
        with mock.patch("llm.client._clients", {"worker": fake, "reasoning": fake}):
            yield fake

    return _patch()


class TempDBTestCase(unittest.TestCase):
    """Base class: each test runs against its own throwaway SQLite DB."""

    def setUp(self) -> None:
        self._tmpdir = tempfile.mkdtemp(prefix="agente_test_")
        self._orig_db = settings.DATABASE_PATH
        self._orig_prop = settings.PROPOSALS_OUTPUT_DIR
        settings.DATABASE_PATH = str(Path(self._tmpdir) / "test.db")
        settings.PROPOSALS_OUTPUT_DIR = str(Path(self._tmpdir) / "proposals")
        init_db()

    def tearDown(self) -> None:
        settings.DATABASE_PATH = self._orig_db
        settings.PROPOSALS_OUTPUT_DIR = self._orig_prop
        import shutil

        shutil.rmtree(self._tmpdir, ignore_errors=True)


# ── fixture builders ──────────────────────────────────────────────────────

def make_business(**overrides) -> Business:
    defaults = dict(
        place_id="node/1",
        name="Test Cafe",
        category="restaurant",
        website=None,
        phone="+255700000000",
        address="Independence Ave",
        latitude=-6.791,
        longitude=39.208,
        social_links=[],
    )
    defaults.update(overrides)
    return Business(**defaults)


def make_website(**overrides) -> WebsiteFindings:
    defaults = dict(
        has_website=False,
        reachable=False,
        is_mobile_friendly=None,
        has_ssl=None,
        signals_found=[],
        signals_missing=[],
        page_html=None,
    )
    defaults.update(overrides)
    return WebsiteFindings(**defaults)


def make_social(**overrides) -> SocialFindings:
    defaults = dict(platforms_found=[], platforms_missing=[], notes=[])
    defaults.update(overrides)
    return SocialFindings(**defaults)


def make_bundle(**overrides) -> ResearchBundle:
    defaults = dict(
        business=make_business(),
        website=make_website(),
        reviews=ReviewFindings(review_count_analyzed=0),
        social=make_social(),
    )
    defaults.update(overrides)
    return ResearchBundle(**defaults)


def make_problems(*problems: str) -> ProblemAnalysis:
    return ProblemAnalysis(
        problems=list(problems),
        reasoning="fixture",
    )


def make_solutions(**overrides) -> SolutionRecommendation:
    defaults = dict(solutions=["Online ordering platform"], potential_value="Medium", reasoning="fixture")
    defaults.update(overrides)
    return SolutionRecommendation(**defaults)


def make_qualification(**overrides) -> QualificationScore:
    defaults = dict(
        business_activity_score=0,
        digital_presence_score=0,
        ability_to_pay_score=5,
        solution_need_score=10,
        total_score=0,
        priority="Low",
        reasoning=[],
    )
    defaults.update(overrides)
    return QualificationScore(**defaults)


def make_reachability(**overrides) -> ReachabilityInfo:
    defaults = dict(email_found=None, contactable_channels=[], reachability_score=0)
    defaults.update(overrides)
    return ReachabilityInfo(**defaults)


def days_ago(n: int) -> str:
    return (date.today() - timedelta(days=n)).isoformat()