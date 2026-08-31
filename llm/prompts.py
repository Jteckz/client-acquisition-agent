"""
All prompt templates in one place. Keeping prompts separate from the code
that calls them makes it much faster to iterate on wording without hunting
through logic files — this matters a lot with smaller Llama models, which
are more sensitive to prompt phrasing than larger hosted models.
"""

REVIEW_ANALYSIS_PROMPT = """You are analyzing customer reviews for a local business.

Reviews:
{reviews}

Identify recurring complaints (operational problems, service issues, things
customers wish existed) and recurring positive themes. Only include a
complaint if it appears in more than one review or is clearly significant.

Return JSON in this exact shape:
{{
  "complaints": ["short phrase", "short phrase"],
  "positive_themes": ["short phrase", "short phrase"]
}}
"""


PRESENCE_SUMMARY_PROMPT = """Summarize this business's online presence in
1-2 plain sentences, based only on the facts given. Do not add opinions or
recommendations — just describe the current state.

Website: {website_summary}
Social: {social_summary}
"""


PROBLEM_DETECTION_PROMPT = """You are a business analyst evaluating whether a
local business is losing opportunities because it lacks a software solution.

Business: {business_name}
Category: {category}

Presence summary (a plain-language overview of the evidence below):
{presence_summary}

Website findings:
{website_findings}

Review findings:
{review_findings}

Social media findings:
{social_findings}

Based ONLY on the evidence above, list the concrete operational or digital
problems this business appears to have. Do not invent problems that aren't
supported by the evidence. If the evidence is too thin to say anything
useful, return an empty list.

Return JSON in this exact shape:
{{
  "problems": ["short problem statement", "short problem statement"],
  "reasoning": "1-2 sentences explaining your read of the evidence"
}}
"""


SOLUTION_RECOMMENDATION_PROMPT = """You are a software consultant. A local
business has been found to have the following problems:

Business: {business_name}
Category: {category}
Problems:
{problems}

Recommend specific, concrete software solutions that would address these
problems (e.g. "Online ordering platform", "WhatsApp booking bot",
"Mobile-friendly website redesign"). Keep each solution to a short phrase.
Then estimate the potential business value of pursuing this lead as a
software project: Low, Medium, or High.

Return JSON in this exact shape:
{{
  "solutions": ["solution", "solution"],
  "potential_value": "Low" | "Medium" | "High",
  "reasoning": "1-2 sentences justifying the value estimate"
}}
"""

# ── V2 prompts ────────────────────────────────────────────────────────

SOLUTION_DESIGN_PROMPT = """You are a solution architect. A business has
these problems:
{problems}

{template_context}

{insight_context}
Select and customize the most relevant package for this business. If a
template was provided, prefer reusing its base_features and only add
optional features that are clearly justified by the problems above — do
not add features without a reason tied to a stated problem. If no template
fits, design a minimal custom package.

Return JSON in this exact shape:
{{
  "package_name": "...",
  "features": ["...", "..."],
  "reasoning": "1-2 sentences"
}}
"""


TECH_STACK_PROMPT = """You are a tech consultant recommending a stack for a
local business software project.

Business category: {category}
Package: {package_name}
Features needed: {features}

Select the best technology stack from the allowed options below. Choose
based on the business's needs — prefer simple, maintainable stacks for
small local businesses. Return the choice as-is from the list.

Allowed stacks:
{allowed_stacks}

Return JSON in this exact shape:
{{
  "frontend": "...",
  "backend": "...",
  "database": "...",
  "hosting": "...",
  "reasoning": "1-2 sentences explaining your choice"
}}
"""


COMPLEXITY_PROMPT = """You are a project estimator. A business needs a
software solution with these features:
{features}

Number of features: {feature_count}

Assess the complexity of this project as Low, Medium, or High based on the
feature count and the nature of the features. Low = simple website or
single-feature app; Medium = multi-feature platform; High = complex system
with many integrations.

Return JSON in this exact shape:
{{
  "complexity": "Low" | "Medium" | "High",
  "reasoning": "1-2 sentences"
}}
"""


EXECUTIVE_SUMMARY_PROMPT = """Write a 2-4 sentence executive summary for a
proposal to {business_name}, a {category} business.

Identified challenges: {challenges}
Proposed solution: {package_name} ({features})

The summary should be professional, concise, and describe the problem, the
proposed solution, and the expected outcome. Do NOT include dollar figures
or timeline numbers — those are covered elsewhere in the proposal.
"""

# ── V3 prompts ────────────────────────────────────────────────────────

RESPONSE_CLASSIFICATION_PROMPT = """You are analyzing a reply received from
a business owner after an outreach message.

Reply text:
{response_text}

Classify the reply into exactly ONE of the statuses below. The "status" field must
contain ONLY one of these exact labels with nothing else:
- Warm Lead
- Future Opportunity
- Not Interested
- Needs More Info
- Converted

Guidance:
- Use "Converted" when the reply asks to proceed, sign, move ahead, or accept or
  receive the full proposal — even if the wording also sounds merely interested.
- Use "Warm Lead" for enthusiastic interest without a concrete next step.
- Use "Future Opportunity" when they are interested but explicitly not ready now.
- Use "Not Interested" for refusals or declines.
- Use "Needs More Info" for questions or requests for details.
- When unsure between two statuses, prefer the more committed one.

Return JSON in this exact shape:
{{
  "status": "one of the five labels above, exactly as written, with no extra words",
  "reasoning": "1-2 sentences"
}}
"""


PERSONALIZATION_HOOK_PROMPT = """You are preparing outreach for a local
business. Below are the specific problems and evidence gathered for THIS
business. Produce ONE sentence that opens outreach by referencing a
specific, concrete finding from the business's own data — never a generic
template phrase. The owner should instantly recognize it is about their
business.

Business: {business_name}
Category: {category}
Problems found:
{problems}

Evidence gathered:
{evidence}

Return JSON in this exact shape:
{{
  "hook": "one sentence referencing a specific finding"
}}
"""


EMAIL_DRAFT_PROMPT = """You are drafting a first-contact email to a local
business owner. Keep the body under 150 words.

Business: {business_name}
Personalization hook: {hook}

Rules:
- Open with the personalization hook; do not restate the full proposal.
- Be concise and professional. No invented claims, no fake urgency, no fake
  social proof, no impersonation, no fake company names.
- Do not include dollar figures or timelines.
- End with a low-pressure call to action, e.g. "open to a short call?"

{followup_context}

Return JSON in this exact shape:
{{
  "subject": "short email subject",
  "body": "email body under 150 words"
}}
"""


LINKEDIN_MESSAGE_PROMPT = """You are drafting a first-contact LinkedIn
message to a local business owner. Keep it under 80 words.

Business: {business_name}
Personalization hook: {hook}

Rules:
- Open with the personalization hook; do not restate the full proposal.
- Concise and professional. No invented claims, fake urgency, fake social
  proof, impersonation, or fake company names.
- End with a low-pressure call to action.

{followup_context}

Return JSON in this exact shape:
{{
  "body": "message under 80 words"
}}
"""


WHATSAPP_DRAFT_PROMPT = """You are drafting a first-contact WhatsApp message
to a local business owner. Keep it under 80 words, friendly and short.

Business: {business_name}
Personalization hook: {hook}

Rules:
- Open with the personalization hook; do not restate the full proposal.
- Concise and professional. No invented claims, fake urgency, fake social
  proof, impersonation, or fake company names.
- End with a low-pressure call to action.

{followup_context}

Return JSON in this exact shape:
{{
  "body": "message under 80 words"
}}
"""


FOLLOWUP_CONTEXT_TEMPLATE = """This is a FOLLOW-UP to a previous message you
sent to this business:
"{original_body}"

Reference the earlier outreach briefly without repeating it verbatim, and
politely ask if they had a chance to consider it.
"""
