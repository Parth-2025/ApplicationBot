import json
from pathlib import Path

import httpx

from discovery.adapters.github_list import (
    GitHubListAdapter,
    SIMPLIFYJOBS_REPO,
    VANSHB03_REPO,
    RELEVANT_CATEGORIES,
)

FIXTURES = Path(__file__).parent / "fixtures"


def _client_returning(fixture_name: str) -> httpx.Client:
    payload = json.loads((FIXTURES / fixture_name).read_text())

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=payload)

    return httpx.Client(transport=httpx.MockTransport(handler))


def test_simplifyjobs_adapter_filters_by_category_and_active():
    client = _client_returning("simplifyjobs_listings_sample.json")
    adapter = GitHubListAdapter(
        repo=SIMPLIFYJOBS_REPO,
        source_name="simplifyjobs_github",
        category_filter=RELEVANT_CATEGORIES,
        client=client,
    )
    postings = adapter.fetch()

    assert len(postings) == 1
    posting = postings[0]
    assert posting.company == "Grant Thornton"
    assert posting.role_title == "Tax Technology Intern - Summer 2027"
    assert posting.source == "simplifyjobs_github"
    assert posting.source_url == (
        "https://ehzq.fa.us2.oraclecloud.com/hcmUI/CandidateExperience/en/sites/CX_1/job/114405"
    )
    assert posting.location == "Bellevue, WA"
    assert posting.raw_description is None


def test_simplifyjobs_adapter_excludes_wrong_category_and_inactive():
    client = _client_returning("simplifyjobs_listings_sample.json")
    adapter = GitHubListAdapter(
        repo=SIMPLIFYJOBS_REPO,
        source_name="simplifyjobs_github",
        category_filter=RELEVANT_CATEGORIES,
        client=client,
    )
    postings = adapter.fetch()
    companies = {p.company for p in postings}
    assert "FHLBank Atlanta" not in companies  # wrong category (Quant)
    assert "Old Corp" not in companies  # inactive


def test_vanshb03_adapter_has_no_category_filter():
    client = _client_returning("vanshb03_listings_sample.json")
    adapter = GitHubListAdapter(
        repo=VANSHB03_REPO,
        source_name="vanshb03_github",
        category_filter=None,
        client=client,
    )
    postings = adapter.fetch()

    assert len(postings) == 2
    companies = {p.company for p in postings}
    assert companies == {"Point72"}
    for posting in postings:
        assert posting.source == "vanshb03_github"


def test_vanshb03_adapter_excludes_inactive():
    client = _client_returning("vanshb03_listings_sample.json")
    adapter = GitHubListAdapter(
        repo=VANSHB03_REPO, source_name="vanshb03_github", category_filter=None, client=client
    )
    postings = adapter.fetch()
    urls = {p.source_url for p in postings}
    assert "https://oldcorp.example.com/jobs/winter-intern" not in urls
