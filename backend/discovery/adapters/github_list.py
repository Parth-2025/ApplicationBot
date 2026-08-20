import json

import httpx

from .base import RawPosting

SIMPLIFYJOBS_REPO = "SimplifyJobs/Summer2027-Internships"
VANSHB03_REPO = "vanshb03/Summer2027-Internships"
RELEVANT_CATEGORIES = {
    "Software Engineering",
    "Software",
    "Data Science, AI & Machine Learning",
    "AI/ML/Data",
}


class GitHubListAdapter:
    def __init__(
        self,
        repo: str,
        source_name: str,
        category_filter: set[str] | None = None,
        client: httpx.Client | None = None,
    ):
        self.repo = repo
        self.source_name = source_name
        self.category_filter = category_filter
        self.listings_url = (
            f"https://raw.githubusercontent.com/{repo}/dev/.github/scripts/listings.json"
        )
        self._client = client or httpx.Client(timeout=30)

    def fetch(self) -> list[RawPosting]:
        response = self._client.get(self.listings_url)
        response.raise_for_status()
        entries = json.loads(response.text)

        postings = []
        for entry in entries:
            if not entry.get("active"):
                continue
            if self.category_filter is not None and entry.get("category") not in self.category_filter:
                continue
            locations = entry.get("locations") or []
            postings.append(
                RawPosting(
                    company=entry["company_name"],
                    role_title=entry["title"],
                    source=self.source_name,
                    source_url=entry["url"],
                    location=", ".join(locations) if locations else None,
                    raw_description=None,
                )
            )
        return postings
