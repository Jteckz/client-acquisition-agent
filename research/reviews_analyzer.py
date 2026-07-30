"""
Review analysis.

OpenStreetMap has no review data — it's a map database, not a review
platform. This module is kept as a separate step (rather than deleted)
because it's a natural place to plug in a review source later without
touching the rest of the pipeline: analysis/lead_scorer.py and
analysis/problem_detector.py already know how to use ReviewFindings if it's
populated.

Options if you want reviews back in a future version:
  - A review platform's official API (most require a paid plan or partner
    access — check current terms before integrating)
  - Manually-collected review text you feed in yourself for priority leads
  - Skipping reviews entirely and leaning harder on website + social
    signals (what V1 does now)

For now this simply returns an empty ReviewFindings so the rest of the
pipeline works unchanged.
"""
from __future__ import annotations

from discovery.models import ReviewFindings


def analyze_reviews(business_place_id: str) -> ReviewFindings:
    return ReviewFindings(review_count_analyzed=0)
