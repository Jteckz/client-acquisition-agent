"""Unit tests for analysis/opportunity_ranker.py.

Run with: python -m unittest tests.test_opportunity_ranker
"""
from __future__ import annotations

import unittest

from analysis.opportunity_ranker import rank_all, rank_opportunity
from discovery.models import QualificationScore, ReachabilityInfo
from storage.db import (
    get_business,
    save_business,
    save_qualification_score,
    save_reachability,
)

from tests.helpers import TempDBTestCase, make_business, make_qualification, make_reachability


def _qual(need: int = 0, budget: int = 0) -> QualificationScore:
    return QualificationScore(
        business_activity_score=0,
        digital_presence_score=0,
        ability_to_pay_score=budget,
        solution_need_score=need,
        total_score=0,
        priority="",
        reasoning=[],
    )


class OpportunityRankerTest(unittest.TestCase):
    def test_all_zero_stays_zero(self):
        ranking = rank_opportunity(_qual(need=0, budget=0), ReachabilityInfo(reachability_score=0))
        self.assertEqual(ranking.final_score, 0)
        self.assertGreaterEqual(ranking.final_score, 0)
        self.assertLessEqual(ranking.final_score, 100)

    def test_all_max_is_100(self):
        ranking = rank_opportunity(
            _qual(need=35, budget=30),
            ReachabilityInfo(contactable_channels=["email", "whatsapp", "facebook", "instagram", "x"], reachability_score=100),
        )
        self.assertEqual(ranking.final_score, 100)
        self.assertGreaterEqual(ranking.final_score, 0)
        self.assertLessEqual(ranking.final_score, 100)

    def test_high_need_low_reachability_ranks_below_reachable(self):
        high_need = rank_opportunity(
            _qual(need=35, budget=15),
            ReachabilityInfo(reachability_score=0),
        )
        reachable = rank_opportunity(
            _qual(need=10, budget=30),
            ReachabilityInfo(contactable_channels=["email"], reachability_score=100),
        )
        self.assertGreater(reachable.final_score, high_need.final_score)

    def test_score_always_within_bounds_for_extremes(self):
        # Push negative / oversized inputs through — must stay clamped.
        ranking = rank_opportunity(
            _qual(need=-50, budget=-50),
            ReachabilityInfo(reachability_score=-10),
        )
        self.assertGreaterEqual(ranking.final_score, 0)
        ranking = rank_opportunity(
            _qual(need=500, budget=500),
            ReachabilityInfo(reachability_score=999),
        )
        self.assertLessEqual(ranking.final_score, 100)


class RankAllTest(TempDBTestCase):
    def test_rank_all_persists_sorts_and_limits(self):
        # high opportunity: strong need + reachable
        save_business(make_business(place_id="node/h", name="Reachable Hotel"))
        save_qualification_score(
            "node/h", make_qualification(solution_need_score=35, ability_to_pay_score=30)
        )
        save_reachability(
            "node/h",
            make_reachability(contactable_channels=["email", "whatsapp"], reachability_score=100),
        )
        # low opportunity: minimal need, no channels
        save_business(make_business(place_id="node/l", name="Low Shop", category="cafe"))
        save_qualification_score(
            "node/l", make_qualification(solution_need_score=10, ability_to_pay_score=5)
        )
        save_reachability("node/l", make_reachability(reachability_score=0))

        rankings = rank_all(limit=20)

        self.assertEqual(len(rankings), 2)
        # sorted descending by final score
        self.assertGreater(rankings[0][2].final_score, rankings[1][2].final_score)
        self.assertEqual(rankings[0][0], "Reachable Hotel")
        # persisted back to the DB
        row = get_business("node/h")
        self.assertIsNotNone(row)

    def test_rank_all_limits_output(self):
        for i in range(5):
            pid = f"node/{i}"
            save_business(make_business(place_id=pid, name=f"Biz {i}"))
            save_qualification_score(
                pid, make_qualification(solution_need_score=10, ability_to_pay_score=5)
            )
            save_reachability(pid, make_reachability(reachability_score=40))
        rankings = rank_all(limit=2)
        self.assertEqual(len(rankings), 2)


if __name__ == "__main__":
    unittest.main()
