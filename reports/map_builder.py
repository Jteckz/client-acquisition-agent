"""
Renders discovered leads onto an interactive map.

Uses Folium — a Python library that generates real Leaflet.js maps as a
single self-contained HTML file. No JavaScript to write, no API key, no
Google Maps dependency: Folium's default tiles come from OpenStreetMap,
which matches the discovery source used in discovery/osm_places.py.

Open the resulting HTML file in any browser.
"""
from __future__ import annotations

import logging
from pathlib import Path

import folium

from discovery.models import LeadReport

logger = logging.getLogger(__name__)

PRIORITY_COLORS = {"High": "red", "Medium": "orange", "Low": "gray"}

OUTPUT_PATH = Path("data") / "leads_map.html"


def build_leads_map(reports: list[LeadReport], output_path: Path | str = OUTPUT_PATH) -> str | None:
    """
    Builds an interactive Leaflet map with one marker per lead, colored by
    priority, with a popup showing score/problems/solutions. Returns the
    path to the saved HTML file, or None if there's nothing to plot.
    """
    plottable = [
        r for r in reports if r.business.latitude is not None and r.business.longitude is not None
    ]
    if not plottable:
        logger.warning("No leads had coordinates to plot — skipping map.")
        return None

    avg_lat = sum(r.business.latitude for r in plottable) / len(plottable)
    avg_lon = sum(r.business.longitude for r in plottable) / len(plottable)

    fmap = folium.Map(location=[avg_lat, avg_lon], zoom_start=13, tiles="OpenStreetMap")

    for report in plottable:
        b = report.business
        popup_html = _build_popup_html(report)
        folium.Marker(
            location=[b.latitude, b.longitude],
            popup=folium.Popup(popup_html, max_width=300),
            tooltip=f"{b.name} — {report.lead_score}/100",
            icon=folium.Icon(color=PRIORITY_COLORS.get(report.priority, "blue"), icon="info-sign"),
        ).add_to(fmap)

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fmap.save(str(output_path))
    logger.info("Saved leads map to %s", output_path)
    return str(output_path)


def _build_popup_html(report: LeadReport) -> str:
    problems = "".join(f"<li>{p}</li>" for p in report.problems) or "<li>None detected</li>"
    solutions = "".join(f"<li>{s}</li>" for s in report.solutions) or "<li>None</li>"
    return f"""
    <b>{report.business.name}</b><br>
    Category: {report.business.category}<br>
    Score: {report.lead_score}/100 ({report.priority})<br>
    <b>Problems:</b><ul>{problems}</ul>
    <b>Suggested solutions:</b><ul>{solutions}</ul>
    """
