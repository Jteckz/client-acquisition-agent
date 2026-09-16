"""
Knowledge base: simple SQL aggregation over the CRM/outreach/proposal data.

This is NOT machine learning — it's plain counts and rates computed from
the local database, matching the spec's example ("40 contacted, 15 replied,
5 converted... online ordering proposals perform best"). Output feeds back
into the V2 solution designer as optional context, but only when a
category has enough sample size to say anything meaningful.
"""
from __future__ import annotations

import logging

from config.settings import settings
from storage.db import get_connection

logger = logging.getLogger(__name__)


def category_conversion_stats() -> list[dict]:
    """Per-category outreach conversion stats.

    For each business category reports: total businesses, contacted count,
    replied count, converted count, conversion rate, and the most common
    proposal package_name among converted leads in that category.
    """
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT b.category,
                   b.place_id,
                   COALESCE(c.pipeline_status, 'New') AS pipeline_status,
                   p.package_name AS package_name,
                   (SELECT COUNT(*) FROM outreach_drafts d
                    WHERE d.place_id = b.place_id AND d.status = 'Sent') AS sent_count,
                   (SELECT COUNT(*) FROM responses r
                    WHERE r.place_id = b.place_id) AS response_count
            FROM businesses b
            LEFT JOIN crm_leads c ON c.place_id = b.place_id
            LEFT JOIN proposals p
                ON p.place_id = b.place_id
                AND p.id = (SELECT MAX(id) FROM proposals p2 WHERE p2.place_id = p.place_id)
            """
        ).fetchall()

    per_category: dict[str, dict] = {}
    for row in rows:
        cat = row["category"] or "unknown"
        bucket = per_category.setdefault(cat, {
            "category": cat,
            "total": 0,
            "contacted": 0,
            "replied": 0,
            "converted": 0,
            "converted_packages": [],
        })
        bucket["total"] += 1
        if row["sent_count"] > 0:
            bucket["contacted"] += 1
        if row["response_count"] > 0:
            bucket["replied"] += 1
        if row["pipeline_status"] == "Won":
            bucket["converted"] += 1
            if row["package_name"]:
                bucket["converted_packages"].append(row["package_name"])

    result = []
    for bucket in per_category.values():
        contacted = bucket["contacted"]
        converted = bucket["converted"]
        rate = round(converted / contacted * 100) if contacted else 0
        common_package = _most_common(bucket["converted_packages"])
        result.append({
            "category": bucket["category"],
            "total": bucket["total"],
            "contacted": contacted,
            "replied": bucket["replied"],
            "converted": converted,
            "conversion_rate": rate,
            "common_package": common_package,
        })
    result.sort(key=lambda d: d["category"])
    return result


def insight_context_for_category(category: str) -> str:
    """Optional context string for the solution designer.

    Returns '' unless the category has >= MIN_SAMPLE_SIZE_FOR_INSIGHTS
    contacted leads — small samples should not influence recommendations.
    """
    for stats in category_conversion_stats():
        if stats["category"] == category:
            if stats["contacted"] >= settings.MIN_SAMPLE_SIZE_FOR_INSIGHTS:
                return (
                    f"Historical note: in past outreach for '{category}' businesses, "
                    f"{stats['converted']}/{stats['contacted']} contacted leads converted "
                    f"({stats['conversion_rate']}%); the most common converted package was "
                    f"{stats['common_package'] or 'n/a'}. Favor proven packages for this category."
                )
            break
    return ""


def print_insights() -> None:
    stats = category_conversion_stats()
    if not stats:
        print("No outreach data yet — run discovery + outreach first.")
        return
    header = f"{'Category':<16} {'Total':<7} {'Contacted':<10} {'Replied':<8} {'Converted':<10} {'Rate':<8} Common converted package"
    print(header)
    print("-" * len(header))
    for s in stats:
        print(
            f"{s['category']:<16} {s['total']:<7} {s['contacted']:<10} {s['replied']:<8} "
            f"{s['converted']:<10} {str(s['conversion_rate']) + '%':<8} {s['common_package'] or '-'}"
        )


def _most_common(items: list[str]) -> str | None:
    if not items:
        return None
    counts: dict[str, int] = {}
    for item in items:
        counts[item] = counts.get(item, 0) + 1
    return max(counts, key=counts.get)
