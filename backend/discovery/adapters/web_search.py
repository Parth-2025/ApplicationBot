import httpx
from bs4 import BeautifulSoup

from ..gemini_client import GeminiClient, GeminiError
from .base import RawPosting

EXTRACTION_PROMPT_TEMPLATE = """You are looking at the text content of a web page found via search for internship postings.

Page URL: {url}
Page text (truncated): {page_text}

If this page is a single specific job/internship posting, respond with ONLY a JSON object (no markdown fence, no other text):
{{
  "is_job_posting": true,
  "company": "the hiring company's name",
  "role_title": "the job title",
  "location": "the job location, or null if not stated",
  "description": "a concise plain-text summary of the posting, 2-4 sentences"
}}

If this page is NOT a single specific job posting (e.g. it's a jobs listing/search page, a company homepage, an article, or an error page), respond with ONLY:
{{"is_job_posting": false}}
"""


class WebSearchAdapter:
    def __init__(
        self,
        queries: list[str],
        google_api_key: str,
        google_cx: str,
        gemini_client: GeminiClient,
        search_client: httpx.Client | None = None,
        page_client: httpx.Client | None = None,
        max_results_per_query: int = 5,
    ):
        self.queries = queries
        self.google_api_key = google_api_key
        self.google_cx = google_cx
        self.gemini_client = gemini_client
        self.max_results_per_query = max_results_per_query
        self._search_client = search_client or httpx.Client(timeout=30)
        self._page_client = page_client or httpx.Client(timeout=30)

    def fetch(self) -> list[RawPosting]:
        postings: list[RawPosting] = []
        for query in self.queries:
            try:
                results = self._search(query)
            except (httpx.HTTPError, ValueError):
                continue
            for item in results[: self.max_results_per_query]:
                posting = self._extract_posting(item["link"])
                if posting is not None:
                    postings.append(posting)
        return postings

    def _search(self, query: str) -> list[dict]:
        response = self._search_client.get(
            "https://www.googleapis.com/customsearch/v1",
            params={"key": self.google_api_key, "cx": self.google_cx, "q": query},
        )
        response.raise_for_status()
        return response.json().get("items", [])

    def _extract_posting(self, url: str) -> RawPosting | None:
        try:
            page_response = self._page_client.get(url)
            page_response.raise_for_status()
        except httpx.HTTPError:
            return None

        page_text = BeautifulSoup(page_response.text, "html.parser").get_text(
            separator=" ", strip=True
        )[:5000]
        prompt = EXTRACTION_PROMPT_TEMPLATE.format(url=url, page_text=page_text)

        try:
            result = self.gemini_client.generate_json(prompt)
        except GeminiError:
            return None

        try:
            if not result.get("is_job_posting"):
                return None

            return RawPosting(
                company=result["company"],
                role_title=result["role_title"],
                source="google_search",
                source_url=url,
                location=result.get("location"),
                raw_description=result.get("description"),
            )
        except (KeyError, AttributeError):
            return None
