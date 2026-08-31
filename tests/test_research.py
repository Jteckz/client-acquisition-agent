"""Phase 2 — Research (V1): website, social, reviews, reachability checks.

Covers research/website_checker.py, research/social_checker.py,
research/reviews_analyzer.py and research/contact_finder.py. HTTP
(requests.get / requests.head) is stubbed; the deterministic helpers are
tested directly.
"""
from __future__ import annotations

import unittest
from unittest import mock

from research import contact_finder, reviews_analyzer, social_checker, website_checker

from tests.helpers import make_bundle, make_social, make_website


class FakeResponse:
    def __init__(self, text: str = "", status: int = 200):
        self.text = text
        self.status_code = status

    def raise_for_status(self):
        if self.status_code >= 400:
            raise AssertionError("unreachable")


class WebsiteCheckerTest(unittest.TestCase):
    def test_no_url_means_no_website(self):
        findings = website_checker.check_website(None)
        self.assertFalse(findings.has_website)
        self.assertFalse(findings.reachable)

    def test_reachable_site_marks_signals_and_mobile(self):
        html = (
            '<html><head><meta name="viewport" content="width=device-width">'
            "</head><body>"
            '<a href="https://facebook.com/biz">fb</a>'
            "<h1>Order now, add to cart, checkout</h1>"
            "<p>Book a table and see our menu</p>"
            "</body></html>"
        )
        with mock.patch(
            "research.website_checker.requests.get",
            return_value=FakeResponse(html),
        ):
            findings = website_checker.check_website("https://example.com/menu")
        self.assertTrue(findings.reachable)
        self.assertTrue(findings.is_mobile_friendly)
        self.assertTrue(findings.has_ssl)
        self.assertIn("online_ordering", findings.signals_found)
        self.assertIn("online_booking", findings.signals_found)
        self.assertIn("online_menu", findings.signals_found)
        self.assertIn("facebook.com/biz", findings.social_links)

    def test_unreachable_site_marks_not_reachable(self):
        class Boom(Exception):
            pass

        def fail(*args, **kwargs):
            raise website_checker.requests.RequestException("refused")

        with mock.patch("research.website_checker.requests.get", side_effect=fail):
            findings = website_checker.check_website("https://example.com")
        self.assertFalse(findings.reachable)
        self.assertTrue(any("unreachable" in n for n in findings.notes))


class SocialCheckerTest(unittest.TestCase):
    def test_extract_social_links_dedupes(self):
        html = (
            'fb="https://facebook.com/a" ig="https://instagram.com/a" '
            'fb2="https://facebook.com/a"'
        )
        links = social_checker.extract_social_links(html)
        # the regex captures the URL without the protocol prefix
        self.assertEqual(links, ["facebook.com/a", "instagram.com/a"])

    def test_identify_platform(self):
        self.assertEqual(
            social_checker._identify_platform("https://x.com/lead"),
            "twitter_x",
        )
        self.assertIsNone(social_checker._identify_platform("https://notsocial.example"))

    def test_reachable_platforms_added_and_missing_tracked(self):
        links = ["facebook.com/a", "instagram.com/b"]
        with mock.patch(
            "research.social_checker._url_reachable", return_value=True
        ):
            findings = social_checker.check_social_presence(links)
        self.assertEqual(set(findings.platforms_found), {"facebook", "instagram"})
        self.assertNotIn("facebook", findings.platforms_missing)

    def test_unreachable_link_not_counted_as_present(self):
        with mock.patch(
            "research.social_checker._url_reachable", return_value=False
        ):
            findings = social_checker.check_social_presence(["facebook.com/a"])
        self.assertEqual(findings.platforms_found, [])
        # the platform was seen (link found) but is unreachable: reported as
        # a note, and it must NOT appear in platforms_found
        self.assertTrue(any("not reachable" in n for n in findings.notes))
        self.assertNotIn("facebook", findings.platforms_found)


class ReviewsAnalyzerTest(unittest.TestCase):
    def test_stub_returns_empty(self):
        findings = reviews_analyzer.analyze_reviews("node/1")
        self.assertEqual(findings.review_count_analyzed, 0)
        self.assertEqual(findings.common_complaints, [])


class ContactFinderTest(unittest.TestCase):
    def test_mailto_link_wins_over_plain_text(self):
        html = (
            '<a href="mailto:hello@cafe.co.tz?subject=Hi">Email</a>'
            "<p>Also contact accounts@cafe.co.tz</p>"
        )
        self.assertEqual(contact_finder._extract_email(html), "hello@cafe.co.tz")

    def test_placeholder_domain_ignored(self):
        html = '<a href="mailto:noreply@example.com">Email</a><p>real@cafe.co.tz</p>'
        self.assertEqual(contact_finder._extract_email(html), "real@cafe.co.tz")

    def test_plain_text_fallback(self):
        self.assertEqual(
            contact_finder._extract_email("<p>Talk to us: sales@cafe.co.tz</p>"),
            "sales@cafe.co.tz",
        )

    def test_no_email_returns_none(self):
        self.assertIsNone(contact_finder._extract_email("<p>No contact here</p>"))

    def test_reachability_score_counts_channels_and_caps(self):
        bundle = make_bundle(
            website=make_website(
                has_website=True,
                reachable=True,
                signals_found=["whatsapp_link"],
                page_html='<a href="mailto:a@cafe.co.tz">a</a>',
            ),
            social=make_social(
                platforms_found=["facebook", "instagram", "x", "tiktok"]
            ),
        )
        reach = contact_finder.find_reachability(bundle)
        self.assertIn("email", reach.contactable_channels)
        self.assertIn("whatsapp", reach.contactable_channels)
        self.assertIn("facebook", reach.contactable_channels)
        # email + whatsapp + 4 socials = 6 channels -> capped at 100
        self.assertEqual(reach.reachability_score, 100)

    def test_no_channels_scores_zero(self):
        reach = contact_finder.find_reachability(make_bundle())
        self.assertEqual(reach.reachability_score, 0)
        self.assertEqual(reach.contactable_channels, [])


if __name__ == "__main__":
    unittest.main()