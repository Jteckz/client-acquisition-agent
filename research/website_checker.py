"""
Website research: does the business have a site, is it reachable, does it
look mobile-friendly, and does it have (or lack) features that matter for
lead scoring — an online menu, a booking form, ecommerce/ordering, etc.

This is intentionally heuristic, not a full Lighthouse audit. It's meant to
give the LLM analysis step enough signal to reason about, not to be a
perfect technical audit.
"""
from __future__ import annotations

import logging
from typing import Optional

import requests
from bs4 import BeautifulSoup

from config.settings import settings
from discovery.models import WebsiteFindings

logger = logging.getLogger(__name__)

# Keyword signals we look for in page text/markup. Extend freely as you learn
# what matters for the business categories you target.
FEATURE_SIGNALS = {
    "online_menu": ["menu", "order online", "our dishes"],
    "online_booking": ["book now", "reserve", "book a table", "appointment", "schedule"],
    "online_ordering": ["order now", "add to cart", "checkout", "delivery"],
    "contact_form": ["contact us", "get in touch"],
    "whatsapp_link": ["wa.me", "whatsapp"],
}


def check_website(url: Optional[str]) -> WebsiteFindings:
    if not url:
        return WebsiteFindings(has_website=False, reachable=False)

    findings = WebsiteFindings(has_website=True)
    findings.has_ssl = url.startswith("https://")

    try:
        resp = requests.get(
            url,
            timeout=settings.REQUEST_TIMEOUT_SECONDS,
            headers={"User-Agent": settings.USER_AGENT},
            allow_redirects=True,
        )
        resp.raise_for_status()
    except requests.RequestException as exc:
        findings.reachable = False
        findings.notes.append(f"Site unreachable: {exc}")
        return findings

    findings.reachable = True
    findings.page_html = resp.text  # kept transient for contact_finder to reuse — not persisted
    soup = BeautifulSoup(resp.text, "lxml")

    from research.social_checker import extract_social_links  # local import avoids a cycle at module load
    findings.social_links = extract_social_links(resp.text)

    findings.title = soup.title.string.strip() if soup.title and soup.title.string else None
    findings.is_mobile_friendly = _has_viewport_meta(soup)

    page_text = soup.get_text(separator=" ", strip=True).lower()
    for signal_name, keywords in FEATURE_SIGNALS.items():
        if any(kw in page_text for kw in keywords):
            findings.signals_found.append(signal_name)
        else:
            findings.signals_missing.append(signal_name)

    if not findings.is_mobile_friendly:
        findings.notes.append("No responsive viewport meta tag found — likely not mobile-friendly")

    return findings


def _has_viewport_meta(soup: BeautifulSoup) -> bool:
    tag = soup.find("meta", attrs={"name": "viewport"})
    return tag is not None
