"""Core data model for a business record as it flows through the pipeline."""
from __future__ import annotations

from typing import Optional
from pydantic import BaseModel, Field


class Business(BaseModel):
    """A single business discovered from a source (Google Places, etc.)."""

    place_id: str = Field(..., description="Unique ID from the source, used for dedup")
    name: str
    category: str = ""
    website: Optional[str] = None
    phone: Optional[str] = None
    address: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    rating: Optional[float] = None
    rating_count: Optional[int] = None
    social_links: list[str] = Field(default_factory=list)
    source: str = "google_places"


class WebsiteFindings(BaseModel):
    """Result of analyzing a business's website (or lack thereof)."""

    has_website: bool = False
    reachable: bool = False
    is_mobile_friendly: Optional[bool] = None
    has_ssl: Optional[bool] = None
    title: Optional[str] = None
    signals_found: list[str] = Field(default_factory=list)  # e.g. "online_menu", "booking_form"
    signals_missing: list[str] = Field(default_factory=list)
    social_links: list[str] = Field(default_factory=list)  # scraped from the site itself
    notes: list[str] = Field(default_factory=list)


class ReviewFindings(BaseModel):
    """Result of analyzing recent Google reviews for a business."""

    review_count_analyzed: int = 0
    average_rating: Optional[float] = None
    common_complaints: list[str] = Field(default_factory=list)
    positive_themes: list[str] = Field(default_factory=list)
    raw_snippets: list[str] = Field(default_factory=list)


class SocialFindings(BaseModel):
    """Result of checking social media presence."""

    platforms_found: list[str] = Field(default_factory=list)
    platforms_missing: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


class ResearchBundle(BaseModel):
    """All raw research gathered on one business, before LLM analysis."""

    business: Business
    website: WebsiteFindings
    reviews: ReviewFindings
    social: SocialFindings


class ProblemAnalysis(BaseModel):
    """LLM output: detected problems for a business."""

    problems: list[str] = Field(default_factory=list)
    reasoning: str = ""


class SolutionRecommendation(BaseModel):
    """LLM output: recommended software solutions for detected problems."""

    solutions: list[str] = Field(default_factory=list)
    potential_value: str = "Unknown"  # Low / Medium / High
    reasoning: str = ""


class LeadReport(BaseModel):
    """Final assembled report for one business, matching the project spec."""

    business: Business
    website: WebsiteFindings
    reviews: ReviewFindings
    social: SocialFindings
    problems: list[str]
    solutions: list[str]
    potential_value: str
    lead_score: int
    priority: str  # Low / Medium / High
    score_reasons: list[str]
