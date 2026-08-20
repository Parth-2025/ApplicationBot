import html

import httpx
from bs4 import BeautifulSoup

from ..config import CompanyBoardConfig
from .base import RawPosting


def _clean_html(raw_html: str) -> str:
    unescaped = html.unescape(raw_html)
    return BeautifulSoup(unescaped, "html.parser").get_text(separator=" ", strip=True)


class JobBoardAdapter:
    def __init__(self, companies: list[CompanyBoardConfig], client: httpx.Client | None = None):
        self.companies = companies
        self._client = client or httpx.Client(timeout=30)

    def fetch(self) -> list[RawPosting]:
        postings: list[RawPosting] = []
        for company in self.companies:
            try:
                postings.extend(self._fetch_company(company))
            except httpx.HTTPStatusError:
                continue
        return postings

    def _fetch_company(self, company: CompanyBoardConfig) -> list[RawPosting]:
        if company.board_type == "greenhouse":
            return self._fetch_greenhouse(company)
        if company.board_type == "lever":
            return self._fetch_lever(company)
        raise ValueError(f"Unknown board_type: {company.board_type!r}")

    def _fetch_greenhouse(self, company: CompanyBoardConfig) -> list[RawPosting]:
        url = f"https://boards-api.greenhouse.io/v1/boards/{company.board_slug}/jobs?content=true"
        response = self._client.get(url)
        response.raise_for_status()
        data = response.json()
        postings = []
        for job in data.get("jobs", []):
            postings.append(
                RawPosting(
                    company=job.get("company_name", company.name),
                    role_title=job["title"],
                    source="greenhouse",
                    source_url=job["absolute_url"],
                    location=(job.get("location") or {}).get("name"),
                    raw_description=_clean_html(job.get("content", "")) or None,
                )
            )
        return postings

    def _fetch_lever(self, company: CompanyBoardConfig) -> list[RawPosting]:
        url = f"https://api.lever.co/v0/postings/{company.board_slug}?mode=json"
        response = self._client.get(url)
        response.raise_for_status()
        data = response.json()
        postings = []
        for job in data:
            categories = job.get("categories") or {}
            postings.append(
                RawPosting(
                    company=company.name,
                    role_title=job["text"],
                    source="lever",
                    source_url=job["hostedUrl"],
                    location=categories.get("location"),
                    raw_description=job.get("descriptionPlain") or None,
                )
            )
        return postings
