from dataclasses import dataclass

from .adapters.base import RawPosting
from .gemini_client import GeminiClient, GeminiError

CLASSIFY_PROMPT_TEMPLATE = """You are screening a job posting for a college student's Summer 2027 internship search (AI engineering, ML engineering, or software engineering roles only).

Posting:
Company: {company}
Role title: {role_title}
Location: {location}
Description: {raw_description}

Some postings above have no description text available - judge from the title/company/location alone in that case.

Answer with ONLY a JSON object (no other text, no markdown fence) with exactly these keys:
{{
  "still_open": true or false (assume true unless something indicates the posting is closed/expired),
  "is_summer_2027": true or false (must be for a Summer 2027 internship specifically, not Summer 2026/2028 or a different term),
  "is_paid": true or false (default true unless explicitly unpaid/volunteer),
  "is_us_based": true or false (based on the location, or the description if location is missing),
  "eligibility": one of "soph_junior", "all_levels", "freshman_only", "senior_only", "other" (default "all_levels" when there is no explicit statement restricting eligibility by class year; only use "freshman_only" or "senior_only" when the posting explicitly restricts to that class year alone),
  "role_category": "swe_ai_ml" if this is a software engineering, AI engineering, or ML engineering role, otherwise "other" (e.g. quant, hardware, product, sales, finance, etc. are "other")
}}
"""


@dataclass
class ClassificationResult:
    passed: bool
    eligibility: str
    paid: bool


def classify_posting(client: GeminiClient, posting: RawPosting) -> ClassificationResult | None:
    prompt = CLASSIFY_PROMPT_TEMPLATE.format(
        company=posting.company,
        role_title=posting.role_title,
        location=posting.location or "unknown",
        raw_description=posting.raw_description or "(no description available)",
    )
    try:
        result = client.generate_json(prompt)
    except GeminiError:
        return None

    eligibility = result.get("eligibility", "other")
    passed = (
        result.get("still_open") is True
        and result.get("is_summer_2027") is True
        and result.get("is_paid") is True
        and result.get("is_us_based") is True
        and eligibility in ("soph_junior", "all_levels")
        and result.get("role_category") == "swe_ai_ml"
    )
    return ClassificationResult(
        passed=passed,
        eligibility=eligibility,
        paid=bool(result.get("is_paid", False)),
    )
