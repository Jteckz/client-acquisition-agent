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
    page_html: Optional[str] = None  # raw HTML of the fetched homepage (transient, reused by contact_finder)


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


# ── V2 models ──────────────────────────────────────────────────────────

class SolutionBlueprint(BaseModel):
    """Output of the Solution Design Engine."""
    package_name: str
    features: list[str]
    reasoning: str = ""


class TechStack(BaseModel):
    frontend: str
    backend: str
    database: str
    hosting: str
    reasoning: str = ""


class ComplexityEstimate(BaseModel):
    """LLM-assessed complexity label — NOT a dollar figure."""
    complexity: str  # Low | Medium | High
    feature_count: int
    reasoning: str = ""


class CostEstimate(BaseModel):
    complexity: str
    estimated_weeks_min: int
    estimated_weeks_max: int
    estimated_cost_min: int
    estimated_cost_max: int
    currency: str = "USD"


class QualificationScore(BaseModel):
    business_activity_score: int
    digital_presence_score: int
    ability_to_pay_score: int
    solution_need_score: int
    total_score: int
    priority: str
    reasoning: list[str]


class ProposalDocument(BaseModel):
    business_name: str
    executive_summary: str
    identified_challenges: list[str]
    proposed_solution: SolutionBlueprint
    tech_stack: TechStack
    cost_estimate: CostEstimate
    expected_benefits: list[str]
    status: str = "Draft"
    pdf_path: str | None = None


# ── V3 models ──────────────────────────────────────────────────────────

class ReachabilityInfo(BaseModel):
    email_found: str | None = None
    contactable_channels: list[str] = Field(default_factory=list)  # e.g. ["email", "whatsapp", "facebook"]
    reachability_score: int = 0  # 0-100, computed deterministically


class OpportunityRanking(BaseModel):
    need_score: int
    budget_score: int
    reachability_score: int
    final_score: int
    rank_reasoning: list[str]


class OutreachDraft(BaseModel):
    place_id: str
    channel: str  # "email" | "linkedin" | "whatsapp"
    subject: str | None = None  # email only
    personalization_hook: str
    body: str
    status: str = "Pending Approval"  # Pending Approval -> Approved -> Sent -> Rejected
    created_at: str | None = None
    approved_at: str | None = None
    sent_at: str | None = None


class ResponseRecord(BaseModel):
    place_id: str
    outreach_draft_id: int
    response_text: str
    classified_status: str
    analyzed_at: str | None = None


class CRMLead(BaseModel):
    place_id: str
    pipeline_status: str  # New | Qualified | Proposal Sent | Contacted | Warm |
                          # Future Opportunity | Not Interested | Won | Lost
    interest_level: str = "Unknown"  # Unknown | Low | Medium | High
    last_contact_date: str | None = None
    next_follow_up_date: str | None = None
