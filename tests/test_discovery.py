"""Phase 1 — Discovery (V1): OpenStreetMap search, query parsing, mapping.

Covers discovery/osm_places.py. Network calls to Nominatim/Overpass are
stubbed so the phase is exercised offline.
"""
from __future__ import annotations

import unittest
from unittest import mock

import requests

from discovery import osm_places
from discovery.models import Business


class ParseQueryTest(unittest.TestCase):
    def test_valid_query_parses_category_and_location(self):
        category, location = osm_places.parse_query("restaurants in Dar es Salaam")
        self.assertEqual(category, "restaurant")
        self.assertEqual(location, "dar es salaam")  # parse_query lowercases the whole query

    def test_singular_category_phrase_matches(self):
        category, location = osm_places.parse_query("cafe in Arusha")
        self.assertEqual(category, "cafe")
        self.assertEqual(location, "arusha")

    def test_missing_in_raises(self):
        with self.assertRaises(ValueError):
            osm_places.parse_query("restaurants dar es salaam")

    def test_unknown_category_raises(self):
        with self.assertRaises(ValueError) as ctx:
            osm_places.parse_query("quantum farms in Arusha")
        self.assertIn("Supported categories", str(ctx.exception))

    def test_supported_categories_returned_sorted(self):
        cats = osm_places.list_supported_categories()
        self.assertEqual(cats, sorted(cats))
        self.assertIn("restaurant", cats)


class ElementToBusinessTest(unittest.TestCase):
    def test_node_element_maps_fields(self):
        el = {
            "type": "node",
            "id": 282,
            "lat": -6.8,
            "lon": 39.2,
            "tags": {
                "name": "Uchumi Cafe",
                "website": "https://example.org",
                "phone": "+255",
                "addr:street": "Main Road",
                "addr:city": "Dar es Salaam",
                "contact:facebook": "facebook.com/uchumi",
            },
        }
        b = osm_places._element_to_business(el, "restaurant")
        self.assertEqual(b.place_id, "node/282")
        self.assertEqual(b.name, "Uchumi Cafe")
        self.assertEqual(b.category, "restaurant")
        self.assertEqual(b.website, "https://example.org")
        self.assertEqual(b.phone, "+255")
        self.assertEqual(b.address, "Main Road, Dar es Salaam")
        self.assertEqual(b.latitude, -6.8)
        # social links come from OSM contact:* tags
        self.assertIn("facebook.com/uchumi", b.social_links)

    def test_way_element_uses_center_for_coordinates(self):
        el = {
            "type": "way",
            "id": 777,
            "center": {"lat": 1.5, "lon": 2.5},
            "tags": {"name": "Hotel Special", "website": "https://h.example"},
        }
        b = osm_places._element_to_business(el, "hotel")
        self.assertEqual(b.place_id, "way/777")
        self.assertEqual((b.latitude, b.longitude), (1.5, 2.5))

    def test_no_website_tag_defaults_none(self):
        b = osm_places._element_to_business(
            {"type": "node", "id": 1, "lat": 0, "lon": 0, "tags": {"name": "X"}},
            "cafe",
        )
        self.assertIsNone(b.website)


class SearchBusinessesTest(unittest.TestCase):
    def test_returns_mapped_businesses_and_respects_limit(self):
        osm_element = {
            "type": "node",
            "id": 1,
            "lat": -6.8,
            "lon": 39.2,
            "tags": {"name": "A"},
        }
        overpass_payload = {"elements": [osm_element] * 5}
        with mock.patch(
            "discovery.osm_places.geocode_location", return_value=(-6.8, 39.2)
        ), mock.patch(
            "discovery.osm_places._run_overpass_query", return_value=overpass_payload
        ), mock.patch("discovery.osm_places.time.sleep", return_value=None):
            results = osm_places.search_businesses("restaurant", "X", max_results=3)
        self.assertEqual(len(results), 3)
        self.assertTrue(all(isinstance(r, Business) for r in results))
        self.assertEqual(results[0].place_id, "node/1")

    def test_unnamed_polygons_are_filtered(self):
        osm_element = {
            "type": "node",
            "id": 1,
            "lat": 0,
            "lon": 0,
            "tags": {},  # no name -> "Unnamed" -> filtered
        }
        overpass_payload = {"elements": [osm_element, osm_element]}
        with mock.patch(
            "discovery.osm_places.geocode_location", return_value=(0, 0)
        ), mock.patch(
            "discovery.osm_places._run_overpass_query", return_value=overpass_payload
        ), mock.patch("discovery.osm_places.time.sleep", return_value=None):
            results = osm_places.search_businesses("restaurant", "X", max_results=10)
        self.assertEqual(results, [])

    def test_unknown_category_raises_before_network(self):
        with mock.patch(
            "discovery.osm_places._run_overpass_query",
            side_effect=AssertionError("network called"),
        ), self.assertRaises(ValueError):
            osm_places.search_businesses("warp drive", "X")


class OverpassMirrorTest(unittest.TestCase):
    def test_falls_back_to_mirror_when_primary_fails(self):
        calls: list[str] = []

        class FakeResp:
            def __init__(self, url):
                self._ok = "overpass-api.de" not in url

            def raise_for_status(self):
                if not self._ok:
                    raise requests.exceptions.HTTPError("504 Server Error")

            def json(self):
                return {"elements": []}

        def fake_post(url, *args, **kwargs):
            calls.append(url)
            return FakeResp(url)

        with mock.patch("discovery.osm_places.requests.post", side_effect=fake_post):
            result = osm_places._run_overpass_query("data")

        self.assertEqual(result, {"elements": []})
        self.assertGreater(len(calls), 1)  # primary failed, next mirror succeeded
        self.assertEqual(calls[0], osm_places.OVERPASS_URLS[0])

    def test_all_endpoints_down_raises(self):
        class FakeResp:
            def raise_for_status(self):
                raise requests.exceptions.HTTPError("503 Service Unavailable")

            def json(self):
                return {}

        with mock.patch(
            "discovery.osm_places.requests.post", return_value=FakeResp()
        ), self.assertRaises(requests.exceptions.HTTPError):
            osm_places._run_overpass_query("data")


if __name__ == "__main__":
    unittest.main()