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


PROBLEM_DETECTION_PROMPT = """You are a business analyst evaluating whether a
local business is losing opportunities because it lacks a software solution.

Business: {business_name}
Category: {category}

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
