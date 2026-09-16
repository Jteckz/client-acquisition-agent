"""Phase 4 — Solution design & tech recommendation & cost estimation (V2)."""
from __future__ import annotations

import unittest

from analysis.cost_estimator import estimate_cost
from analysis.solution_designer import design_solution
from analysis.tech_recommender import ALLOWED_STACKS, recommend_tech_stack
from discovery.models import SolutionBlueprint
from solutions import library

from tests.helpers import make_problems, patch_llm


def _blueprint(name="Restaurant Digital Platform", features=None):
    return SolutionBlueprint(
        package_name=name,
        features=features or ["Website", "Digital Menu", "Online Ordering", "WhatsApp Integration"],
        reasoning="fixture",
    )


class SolutionDesignerTest(unittest.TestCase):
    def test_uses_template_for_known_category(self):
        with patch_llm([("Available template 'Restaurant Digital Platform'", {
            "package_name": "Restaurant Digital Platform",
            "features": ["Website", "Online Ordering"],
            "reasoning": "chosen",
        })]):
            blueprint, template = design_solution("restaurant", make_problems("No site"))
        self.assertEqual(blueprint.package_name, "Restaurant Digital Platform")
        self.assertIsNotNone(template)
        self.assertEqual(template["package_name"], "Restaurant Digital Platform")

    def test_no_template_for_unknown_category(self):
        with patch_llm([("No template available", {
            "package_name": "Custom Solution",
            "features": ["Website"],
            "reasoning": "",
        })]):
            blueprint, template = design_solution("zorb-laser-arena", make_problems("No site"))
        self.assertIsNone(template)
        self.assertEqual(blueprint.package_name, "Custom Solution")

    def test_defaults_when_llm_returns_empty(self):
        with patch_llm([]):
            blueprint, _ = design_solution("gym", make_problems("No site"))
        self.assertEqual(blueprint.package_name, "Custom Solution")


class TechRecommenderTest(unittest.TestCase):
    def test_template_default_stack_used_without_llm(self):
        template = library.load_template("restaurant")
        with patch_llm([]) as fake:
            stack = recommend_tech_stack("restaurant", _blueprint(), template)
            calls = list(fake.generate_json_calls)
        self.assertEqual(stack.frontend, "React")
        self.assertEqual(calls, [])

    def test_allowed_llm_stack_accepted(self):
        chosen = ALLOWED_STACKS[1]
        with patch_llm([("best technology stack", {
            **chosen, "reasoning": "picked",
        })]):
            # "gym" has no template, so the LLM path is taken
            stack = recommend_tech_stack("gym", _blueprint())
        self.assertEqual(stack.backend, "Django")
        self.assertEqual(stack.reasoning, "picked")

    def test_unallowed_stack_falls_back(self):
        with patch_llm([("best technology stack", {
            "frontend": "Angular", "backend": "Rails", "database": "Oracle", "hosting": "Azure",
        })]):
            stack = recommend_tech_stack("restaurant", _blueprint())
        self.assertEqual(stack.frontend, ALLOWED_STACKS[0]["frontend"])
        self.assertIn("fell back", stack.reasoning.lower())


class CostEstimatorTest(unittest.TestCase):
    def _default_template(self):
        return library.load_template("restaurant")

    def test_high_complexity_multiples_base(self):
        template = self._default_template()  # base_cost [1500,2500], base_weeks [3,5]
        bp = _blueprint(features=["Website", "Digital Menu", "Online Ordering", "WhatsApp Integration"])
        with patch_llm([("Number of features", {"complexity": "High"})]):
            cost = estimate_cost(bp, template)
        # extra_features = len(bp.features) - 4 template features = 0
        self.assertEqual(cost.estimated_cost_min, 2100)   # 1500 * 1.4
        self.assertEqual(cost.estimated_cost_max, 3500)   # 2500 * 1.4
        self.assertEqual(cost.estimated_weeks_min, 4)     # round(3*1.4)
        self.assertEqual(cost.estimated_weeks_max, 7)     # round(5*1.4)

    def test_extra_features_increment_cost_and_weeks(self):
        template = self._default_template()
        bp = SolutionBlueprint(
            package_name="P",
            features=["Website", "Digital Menu", "Online Ordering", "WhatsApp Integration",
                      "Loyalty", "Analytics", "Reservations"],  # 3 extra features
            reasoning="",
        )
        with patch_llm([("Number of features", {"complexity": "Medium"})]):
            cost = estimate_cost(bp, template)
        # extra 3: cost +3*150 = 450 min, +3*250=750 max; weeks +1 on max (>2 extras)
        self.assertEqual(cost.estimated_cost_min, 1500 + 450)
        self.assertEqual(cost.estimated_cost_max, 2500 + 750)
        self.assertEqual(cost.estimated_weeks_max, 5 + 1)

    def test_invalid_complexity_label_defaults_medium(self):
        with patch_llm([("Number of features", {"complexity": "Cosmic"})]):
            cost = estimate_cost(_blueprint(features=["A", "B"]), None)
        self.assertEqual(cost.complexity, "Medium")

    def test_low_high_monotonicity(self):
        with patch_llm([("Number of features", {"complexity": "Low"})]):
            low = estimate_cost(_blueprint(features=["A"]), None)
        with patch_llm([("Number of features", {"complexity": "High"})]):
            high = estimate_cost(_blueprint(features=["A"]), None)
        self.assertLess(low.estimated_cost_min, high.estimated_cost_min)


class SolutionLibraryTest(unittest.TestCase):
    def test_known_template_loads(self):
        template = library.load_template("restaurant")
        self.assertEqual(template["package_name"], "Restaurant Digital Platform")

    def test_alias_maps_to_shared_template(self):
        self.assertEqual(library.load_template("cafe")["package_name"], "Restaurant Digital Platform")

    def test_unknown_category_returns_none(self):
        self.assertIsNone(library.load_template("gym"))

    def test_list_templates_contains_restaurant(self):
        self.assertIn("restaurant", library.list_templates())


if __name__ == "__main__":
    unittest.main()