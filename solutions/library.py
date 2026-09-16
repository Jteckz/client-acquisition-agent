from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"

CATEGORY_TEMPLATE_MAP: dict[str, str] = {
    "restaurant": "restaurant.yaml",
    "cafe": "restaurant.yaml",
    "fast food": "restaurant.yaml",
    "bar": "restaurant.yaml",
    "hotel": "hotel.yaml",
    "guesthouse": "hotel.yaml",
    "school": "school.yaml",
    "college": "school.yaml",
    "hospital": "hospital.yaml",
    "clinic": "hospital.yaml",
    "pharmacy": "hospital.yaml",
    "dentist": "hospital.yaml",
    "real estate": "real_estate.yaml",
}

_cache: dict[str, dict[str, Any]] = {}


def load_template(category_key: str) -> dict[str, Any] | None:
    filename = CATEGORY_TEMPLATE_MAP.get(category_key)
    if not filename:
        return None
    if filename in _cache:
        return _cache[filename]
    path = TEMPLATES_DIR / filename
    if not path.exists():
        return None
    with open(path) as f:
        data: dict = yaml.safe_load(f)
    _cache[filename] = data
    return data


def list_templates() -> list[str]:
    return sorted(CATEGORY_TEMPLATE_MAP.keys())
