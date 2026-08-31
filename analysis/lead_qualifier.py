from __future__ import annotations

from discovery.models import ProblemAnalysis, QualificationScore, ResearchBundle

POINTS = {
    "business_activity_active": 20,
    "business_activity_inactive": -20,
    "digital_presence_strong": 15,
    "digital_presence_weak": -10,
    "ability_to_pay_high": 30,
    "ability_to_pay_medium": 15,
    "ability_to_pay_low": 5,
    "solution_need_critical": 35,
    "solution_need_minor": 10,
}


def qualify_lead(bundle: ResearchBundle, problems: ProblemAnalysis) -> QualificationScore:
    business_activity = _score_business_activity(bundle)
    digital_presence = _score_digital_presence(bundle)
    ability_to_pay = _score_ability_to_pay(bundle)
    solution_need = _score_solution_need(bundle, problems)

    total = business_activity + digital_presence + ability_to_pay + solution_need
    total = max(0, min(100, total))

    priority = _priority_for_score(total)

    reasons: list[str] = []
    if business_activity > 0:
        reasons.append("Active business (phone + website/social found)")
    elif business_activity < 0:
        reasons.append("Inactive or hard-to-reach business")
    if digital_presence > 0:
        reasons.append("Strong digital presence")
    else:
        reasons.append("Weak digital presence")
    if ability_to_pay >= 15:
        reasons.append("Appears able to invest in solutions")
    if solution_need >= 35:
        reasons.append("Critical need for software solutions")
    else:
        reasons.append("Minor solution needs")

    return QualificationScore(
        business_activity_score=business_activity,
        digital_presence_score=digital_presence,
        ability_to_pay_score=ability_to_pay,
        solution_need_score=solution_need,
        total_score=total,
        priority=priority,
        reasoning=reasons,
    )


def _score_business_activity(bundle: ResearchBundle) -> int:
    has_phone = bool(bundle.business.phone)
    has_reachable_website = bundle.website.has_website and bundle.website.reachable
    has_social = bool(bundle.social.platforms_found)
    if has_phone and (has_reachable_website or has_social):
        return POINTS["business_activity_active"]
    return POINTS["business_activity_inactive"]


def _score_digital_presence(bundle: ResearchBundle) -> int:
    has_website = bundle.website.has_website and bundle.website.reachable
    mobile_friendly = bundle.website.is_mobile_friendly is True
    has_social = bool(bundle.social.platforms_found)
    if has_website and mobile_friendly and has_social:
        return POINTS["digital_presence_strong"]
    return POINTS["digital_presence_weak"]


def _score_ability_to_pay(bundle: ResearchBundle) -> int:
    category = bundle.business.category.lower()
    has_phone = bool(bundle.business.phone)
    has_website = bool(bundle.business.website)
    high_value_categories = {"hotel", "hospital", "school", "college", "real estate", "law firm", "bank"}
    if category in high_value_categories and has_phone and has_website:
        return POINTS["ability_to_pay_high"]
    if has_phone:
        return POINTS["ability_to_pay_medium"]
    return POINTS["ability_to_pay_low"]


def _score_solution_need(bundle: ResearchBundle, problems: ProblemAnalysis) -> int:
    if len(problems.problems) >= 2:
        return POINTS["solution_need_critical"]
    return POINTS["solution_need_minor"]


def _priority_for_score(score: int) -> str:
    if score >= 70:
        return "High"
    if score >= 40:
        return "Medium"
    return "Low"
