"""
Business discovery via OpenStreetMap — no API key required.

Two free public services do the work:
  - Nominatim: turns a place name ("Dar es Salaam") into coordinates
  - Overpass API: queries OSM for businesses matching a tag (e.g.
    amenity=restaurant) within a radius of those coordinates

Both are community-run and rate-limited (be polite: 1 request/second,
identify yourself with a real User-Agent — both already handled below).
For heavier production use later, consider self-hosting Overpass or using
a paid OSM data provider — but for V1 discovery volume this is plenty.
"""
from __future__ import annotations

import logging
import time
from typing import Optional

import requests
from tenacity import retry, stop_after_attempt, wait_exponential

from config.settings import settings
from discovery.models import Business

logger = logging.getLogger(__name__)

NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
OVERPASS_URLS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.osm.ch/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
]
OVERPASS_USER_AGENT = "ClientAcquisitionAgent/1.0"

# Maps a friendly category name -> list of (OSM key, OSM value) tag pairs.
# A category can map to more than one tag pair (e.g. "salon" covers both
# hairdressers and beauty shops). Extend this as you target new categories.
CATEGORY_TAGS: dict[str, list[tuple[str, str]]] = {
    "restaurant": [("amenity", "restaurant")],
    "cafe": [("amenity", "cafe")],
    "fast food": [("amenity", "fast_food")],
    "bar": [("amenity", "bar")],
    "hotel": [("tourism", "hotel")],
    "guesthouse": [("tourism", "guest_house")],
    "school": [("amenity", "school")],
    "college": [("amenity", "college")],
    "hospital": [("amenity", "hospital")],
    "clinic": [("amenity", "clinic")],
    "pharmacy": [("amenity", "pharmacy")],
    "dentist": [("amenity", "dentist")],
    "salon": [("shop", "hairdresser"), ("shop", "beauty")],
    "hair salon": [("shop", "hairdresser")],
    "supermarket": [("shop", "supermarket")],
    "grocery": [("shop", "convenience"), ("shop", "grocery")],
    "bank": [("amenity", "bank")],
    "real estate": [("office", "estate_agent")],
    "gym": [("leisure", "fitness_centre")],
    "car repair": [("shop", "car_repair")],
    "bakery": [("shop", "bakery")],
    "clothing store": [("shop", "clothes")],
    "electronics store": [("shop", "electronics")],
    "furniture store": [("shop", "furniture")],
    "law firm": [("office", "lawyer")],
    "accountant": [("office", "accountant")],
}


def list_supported_categories() -> list[str]:
    return sorted(CATEGORY_TAGS.keys())


def parse_query(query: str) -> tuple[str, str]:
    """
    Parses a free-text query like "restaurants in Dar es Salaam" into
    (category_key, location_name). Raises ValueError with a helpful message
    if the category isn't recognized — use --category/--location directly
    to bypass parsing entirely.
    """
    if " in " not in query.lower():
        raise ValueError(
            f'Could not parse query {query!r}. Use the format "<category> in <location>", '
            f"e.g. \"restaurants in Dar es Salaam\", or pass --category/--location directly."
        )

    category_phrase, location = query.lower().split(" in ", 1)
    category_phrase = category_phrase.strip().rstrip("s")  # naive singularize

    matched = None
    for key in CATEGORY_TAGS:
        if key.rstrip("s") == category_phrase or category_phrase in key:
            matched = key
            break

    if not matched:
        raise ValueError(
            f"Unrecognized category '{category_phrase}'. Supported categories: "
            f"{', '.join(list_supported_categories())}"
        )

    return matched, location.strip()


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=8), reraise=True)
def geocode_location(location_name: str) -> tuple[float, float]:
    """Turns a place name into (latitude, longitude) via Nominatim."""
    resp = requests.get(
        NOMINATIM_URL,
        params={"q": location_name, "format": "json", "limit": 1},
        headers={
            "User-Agent": settings.USER_AGENT,
            "Accept": "*/*",
            "Accept-Encoding": "gzip, deflate",
        },
        timeout=settings.REQUEST_TIMEOUT_SECONDS,
    )
    resp.raise_for_status()
    results = resp.json()
    if not results:
        raise ValueError(f"Could not geocode location: {location_name!r}")
    return float(results[0]["lat"]), float(results[0]["lon"])


@retry(stop=stop_after_attempt(2), wait=wait_exponential(multiplier=1, min=1, max=6), reraise=True)
def _run_overpass_query(ql: str) -> dict:
    """POST the query to the first working Overpass endpoint.

    The public Overpass API is community-run and frequently rate-limits or
    times out (5xx). Try each configured mirror in order, falling through on
    any RequestException, and only raise once every endpoint has failed.
    """
    last_error: Exception | None = None
    for url in OVERPASS_URLS:
        try:
            resp = requests.post(
                url,
                data={"data": ql},
                headers={
                    "User-Agent": OVERPASS_USER_AGENT,
                    "Accept": "*/*",
                },
                timeout=60,
            )
            resp.raise_for_status()
            return resp.json()
        except requests.RequestException as exc:
            logger.warning("Overpass endpoint %s failed (%s) — trying next mirror.", url, exc)
            last_error = exc
    raise last_error or RuntimeError("No Overpass endpoint available")


def search_businesses(
    category: str,
    location: str,
    max_results: Optional[int] = None,
    radius_meters: Optional[int] = None,
) -> list[Business]:
    """
    Search OpenStreetMap for businesses of a given category near a named
    location. `category` must be a key in CATEGORY_TAGS (see
    list_supported_categories()).
    """
    if category not in CATEGORY_TAGS:
        raise ValueError(
            f"Unrecognized category '{category}'. Supported categories: "
            f"{', '.join(list_supported_categories())}"
        )

    max_results = max_results or settings.MAX_RESULTS_PER_SEARCH
    radius = radius_meters or settings.DEFAULT_SEARCH_RADIUS_METERS

    lat, lon = geocode_location(location)
    time.sleep(1)  # be polite to Nominatim before hitting Overpass

    tag_clauses = []
    for key, value in CATEGORY_TAGS[category]:
        tag_clauses.append(f'node["{key}"="{value}"](around:{radius},{lat},{lon});')
        tag_clauses.append(f'way["{key}"="{value}"](around:{radius},{lat},{lon});')

    ql = f"[out:json][timeout:25];\n(\n  " + "\n  ".join(tag_clauses) + "\n);\nout center tags;"

    data = _run_overpass_query(ql)
    elements = data.get("elements", [])

    businesses = [_element_to_business(el, category) for el in elements]
    businesses = [b for b in businesses if b.name != "Unnamed"]  # skip unnamed POIs
    return businesses[:max_results]


def _element_to_business(element: dict, category: str) -> Business:
    tags = element.get("tags", {})

    # Ways/relations don't have direct lat/lon — Overpass gives a "center"
    # when you request `out center`.
    if element["type"] == "node":
        lat, lon = element.get("lat"), element.get("lon")
    else:
        center = element.get("center", {})
        lat, lon = center.get("lat"), center.get("lon")

    address_parts = [
        tags.get("addr:housenumber"),
        tags.get("addr:street"),
        tags.get("addr:suburb"),
        tags.get("addr:city"),
    ]
    address = ", ".join(p for p in address_parts if p) or tags.get("addr:full")

    social_links = [
        tags[key] for key in ("contact:facebook", "contact:instagram", "contact:twitter")
        if tags.get(key)
    ]

    return Business(
        place_id=f"{element['type']}/{element['id']}",
        name=tags.get("name", "Unnamed"),
        category=category,
        website=tags.get("website") or tags.get("contact:website"),
        phone=tags.get("phone") or tags.get("contact:phone"),
        address=address,
        latitude=lat,
        longitude=lon,
        rating=None,       # OSM has no rating data
        rating_count=None, # OSM has no review-count data
        social_links=social_links,
        source="openstreetmap",
    )
