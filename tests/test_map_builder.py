"""Phase 1/3 — Lead map rendering (V1): Folium HTML output.

build_leads_map is fully offline: it only writes a Leaflet HTML file. Leads
without coordinates must be skipped, and an empty result returns None.
"""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from discovery.models import LeadReport
from reports import map_builder

from tests.helpers import make_business, make_social, make_website


def _report(name, lat, lon, priority="High"):
    from discovery.models import ReviewFindings

    return LeadReport(
        business=make_business(
            place_id=name, name=name, latitude=lat, longitude=lon, category="restaurant"
        ),
        website=make_website(),
        reviews=ReviewFindings(review_count_analyzed=0),
        social=make_social(),
        problems=["No website"],
        solutions=["Website builder"],
        potential_value="Medium",
        lead_score=58,
        priority=priority,
        score_reasons=[],
    )


class MapBuilderTest(unittest.TestCase):
    def test_empty_reports_return_none(self):
        self.assertIsNone(map_builder.build_leads_map([]))

    def test_leads_without_coordinates_not_plotted(self):
        report = _report("Nowhere", None, None)
        self.assertIsNone(map_builder.build_leads_map([report]))

    def test_map_html_contains_lead_and_score(self):
        out = Path(tempfile.mkdtemp()) / "map.html"
        result = map_builder.build_leads_map(
            [_report("Cafe One", -6.79, 39.20)], output_path=out
        )
        self.assertEqual(result, str(out))
        html = out.read_text()
        self.assertIn("Cafe One", html)
        self.assertIn("58/100", html)

    def test_popup_html_lists_problems_and_solutions(self):
        html = map_builder._build_popup_html(_report("Cafe One", -6.79, 39.20))
        self.assertIn("<li>No website</li>", html)
        self.assertIn("<li>Website builder</li>", html)


if __name__ == "__main__":
    unittest.main()