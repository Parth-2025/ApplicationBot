import httpx
from bs4 import BeautifulSoup

from ..config import CareerPageConfig
from ..gemini_client import GeminiClient, GeminiError
from .base import RawPosting

EXTRACTION_PROMPT_TEMPLATE = """You are looking at the text content of {company}'s careers page.

Page text (truncated): {page_text}

Find every internship posting on this page that looks like a Summer 2027 AI engineering, ML engineering, or software engineering internship. Respond with ONLY a JSON array (no markdown fence, no other text) of objects, one per posting found:
[
  {{
    "role_title": "the job title",
    "location": "the job location, or null if not stated",
    "description": "a concise plain-text summary of the posting, 2-4 sentences",
    "url": "the direct URL to this specific posting if visible in the page text, otherwise the careers page URL itself"
  }}
]

If you find no such postings on this page, respond with ONLY: []
"""


class CareerPageAdapter:
    def __init__(
        self,
        pages: list[CareerPageConfig],
        gemini_client: GeminiClient,
        client: httpx.Client | None = None,
    ):
        self.pages = pages
        self.gemini_client = gemini_client
        self._client = client or httpx.Client(timeout=30)

    def fetch(self) -> list[RawPosting]:
        postings: list[RawPosting] = []
        for page in self.pages:
            postings.extend(self._fetch_page(page))
        return postings

    def _fetch_page(self, page: CareerPageConfig) -> list[RawPosting]:
        try:
            response = self._client.get(page.url)
            response.raise_for_status()
        except httpx.HTTPError:
            return []

        page_text = BeautifulSoup(response.text, "html.parser").get_text(
            separator=" ", strip=True
        )[:8000]
        prompt = EXTRACTION_PROMPT_TEMPLATE.format(company=page.name, page_text=page_text)

        try:
            results = self.gemini_client.generate_json(prompt)
        except GeminiError:
            return []

        postings = []
        for entry in results:
            try:
                postings.append(
                    RawPosting(
                        company=page.name,
                        role_title=entry["role_title"],
                        source="career_page",
                        source_url=entry.get("url") or page.url,
                        location=entry.get("location"),
                        raw_description=entry.get("description"),
                    )
                )
            except (KeyError, AttributeError, TypeError):
                continue
        return postings
