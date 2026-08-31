"""Phase 6 — Response classification (V3): constrained enum + safe fallback."""
from __future__ import annotations

import unittest

from analysis.response_classifier import FALLBACK_STATUS, RESPONSE_STATUSES, classify_response

from tests.helpers import patch_llm


class ResponseClassifierTest(unittest.TestCase):
    def test_valid_status_passed_through(self):
        with patch_llm([("Reply text:", {"status": "Warm Lead", "reasoning": "interested"})]):
            self.assertEqual(classify_response("We are very interested"), "Warm Lead")

    def test_invalid_status_falls_back(self):
        with patch_llm([("Reply text:", {"status": "Super Hot", "reasoning": ""})]):
            self.assertEqual(classify_response("whatever"), FALLBACK_STATUS)

    def test_empty_llm_output_falls_back(self):
        with patch_llm([("Reply text:", {})]):
            self.assertEqual(classify_response("whatever"), FALLBACK_STATUS)

    def test_all_enum_values_are_valid_outputs(self):
        for status in RESPONSE_STATUSES:
            with patch_llm([("Reply text:", {"status": status})]):
                self.assertEqual(classify_response("hi"), status, f"status={status}")


if __name__ == "__main__":
    unittest.main()