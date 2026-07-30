"""
Social media presence check.

NOTE: Facebook and Instagram both require authenticated access for anything
beyond "does this URL exist" (their public scraping surface is heavily
restricted and scraping them at scale violates their Terms of Service). V1
therefore only checks:

  1. Whether a social link was found at all (from the website or Places data)
  2. Whether that link resolves (HTTP reachable)

For deeper signals (posting frequency, engagement, unanswered comments)
you'd want the official Graph API with a business owner's consent — that's
a good V2 addition, not a V1 scraping hack.
"""
from __future__ import annotations

import logging
import re

import requests

from config.settings import settings
from discovery.models import SocialFindings

logger = logging.getLogger(__name__)

PLATFORM_PATTERNS = {
    "facebook": re.compile(r"facebook\.com/[^\s\"'>]+", re.IGNORECASE),
    "instagram": re.compile(r"instagram\.com/[^\s\"'>]+", re.IGNORECASE),
    "twitter_x": re.compile(r"(twitter\.com|x\.com)/[^\s\"'>]+", re.IGNORECASE),
    "tiktok": re.compile(r"tiktok\.com/[^\s\"'>]+", re.IGNORECASE),
}


def extract_social_links(html_text: str) -> list[str]:
    """Pull social media URLs out of a page's raw HTML."""
    found = []
    for pattern in PLATFORM_PATTERNS.values():
        found.extend(m.group(0) for m in pattern.finditer(html_text))
    return list(dict.fromkeys(found))  # dedupe, preserve order


def check_social_presence(social_links: list[str]) -> SocialFindings:
    findings = SocialFindings()
    seen_platforms = set()

    for link in social_links:
        platform = _identify_platform(link)
        if not platform or platform in seen_platforms:
            continue
        seen_platforms.add(platform)

        reachable = _url_reachable(f"https://{link}" if not link.startswith("http") else link)
        if reachable:
            findings.platforms_found.append(platform)
        else:
            findings.notes.append(f"{platform} link found but not reachable: {link}")

    all_platforms = set(PLATFORM_PATTERNS.keys())
    findings.platforms_missing = sorted(all_platforms - seen_platforms)

    if not findings.platforms_found:
        findings.notes.append("No reachable social media presence detected")

    return findings


def _identify_platform(url: str) -> str | None:
    for name, pattern in PLATFORM_PATTERNS.items():
        if pattern.search(url):
            return name
    return None


def _url_reachable(url: str) -> bool:
    try:
        resp = requests.head(
            url,
            timeout=settings.REQUEST_TIMEOUT_SECONDS,
            headers={"User-Agent": settings.USER_AGENT},
            allow_redirects=True,
        )
        return resp.status_code < 400
    except requests.RequestException:
        return False
