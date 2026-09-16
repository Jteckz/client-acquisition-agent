"""
Reachability check: which channels can we actually reach this business on?

Purely deterministic, reuses data already gathered by the website + social
checks — no new HTTP round-trips. Only PUBLICLY LISTED business contact
info is used (a mailto link or visible email on the business's own site,
a wa.me link, or an already-reachable social platform). We never scrape or
store private individuals' contact details.

Reachability score formula (starting point, tune later against real
outreach outcomes, same spirit as V2's cost table):
    score = 20 * len(contactable_channels), capped at 100
"""
from __future__ import annotations

import logging
import re

from bs4 import BeautifulSoup

from discovery.models import ReachabilityInfo, ResearchBundle

logger = logging.getLogger(__name__)

EMAIL_REGEX = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")

# Emails that are clearly placeholder/throwaway and must never be treated
# as a real contact channel.
PLACEHOLDER_EMAIL_DOMAINS = {
    "example.com", "example.org", "example.net", "yourdomain.com",
    "yourcompany.com", "domain.com", "test.com", "sample.com", "email.com",
}

SCORE_PER_CHANNEL = 20


def find_reachability(bundle: ResearchBundle) -> ReachabilityInfo:
    channels: list[str] = []

    email = None
    page_html = bundle.website.page_html
    if page_html:
        email = _extract_email(page_html)
        if email:
            channels.append("email")

    # wa.me link signal is already detected by website_checker's feature scan.
    if "whatsapp_link" in bundle.website.signals_found:
        channels.append("whatsapp")

    for platform in bundle.social.platforms_found:
        channels.append(platform)

    channels = list(dict.fromkeys(channels))  # dedupe, preserve order

    score = min(100, SCORE_PER_CHANNEL * len(channels))
    return ReachabilityInfo(
        email_found=email,
        contactable_channels=channels,
        reachability_score=score,
    )


def _extract_email(html_text: str) -> str | None:
    soup = BeautifulSoup(html_text, "lxml")

    # Prefer explicit mailto: links — unambiguous intent to receive email.
    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        if href.lower().startswith("mailto:"):
            addr = href.split(":", 1)[1].split("?")[0].strip()
            if "@" in addr and addr.split("@")[1].lower() not in PLACEHOLDER_EMAIL_DOMAINS:
                return addr

    # Fallback: first plausible-looking address in visible text.
    text = soup.get_text(" ", strip=True)
    for match in EMAIL_REGEX.findall(text):
        if match.split("@")[1].lower() not in PLACEHOLDER_EMAIL_DOMAINS:
            return match

    return None
