import json
from pathlib import Path

import httpx
import pytest

from discovery.adapters.job_board import JobBoardAdapter
from discovery.config import CompanyBoardConfig

FIXTURES = Path(__file__).parent / "fixtures"


def _client_with_fixtures():
    greenhouse_payload = json.loads((FIXTURES / "greenhouse_sample.json").read_text())
    lever_payload = json.loads((FIXTURES / "lever_sample.json").read_text())

    def handler(request: httpx.Request) -> httpx.Response:
        if "boards-api.greenhouse.io" in str(request.url):
            return httpx.Response(200, json=greenhouse_payload)
        if "api.lever.co" in str(request.url):
            return httpx.Response(200, json=lever_payload)
        return httpx.Response(404)

    return httpx.Client(transport=httpx.MockTransport(handler))


def test_fetches_and_normalizes_greenhouse_and_lever():
    companies = [
        CompanyBoardConfig(name="GitLab", board_type="greenhouse", board_slug="gitlab"),
        CompanyBoardConfig(name="Zoox", board_type="lever", board_slug="zoox"),
    ]
    adapter = JobBoardAdapter(companies=companies, client=_client_with_fixtures())
    postings = adapter.fetch()

    assert len(postings) == 4  # 2 jobs per board, filtering happens later in the classifier

    gitlab_intern = next(p for p in postings if p.source_url.endswith("8503792002"))
    assert gitlab_intern.company == "GitLab"
    assert gitlab_intern.role_title == "Software Engineering Intern - Summer 2027"
    assert gitlab_intern.source == "greenhouse"
    assert gitlab_intern.location == "Remote, United States"
    assert "Summer 2027 intern" in gitlab_intern.raw_description
    assert "&lt;" not in gitlab_intern.raw_description  # HTML unescaped and tags stripped

    zoox_intern = next(p for p in postings if "f4746da4" in p.source_url)
    assert zoox_intern.company == "Zoox"
    assert zoox_intern.role_title == "Machine Learning Intern - Summer 2027"
    assert zoox_intern.source == "lever"
    assert zoox_intern.location == "Foster City, CA"
    assert zoox_intern.raw_description == (
        "Join Zoox as a Summer 2027 machine learning intern. Open to sophomores and juniors."
    )


def test_unknown_board_type_raises_value_error():
    companies = [CompanyBoardConfig(name="Bad Co", board_type="workday", board_slug="badco")]
    adapter = JobBoardAdapter(companies=companies, client=_client_with_fixtures())
    with pytest.raises(ValueError):
        adapter.fetch()


def test_one_company_failing_does_not_stop_others():
    def handler(request: httpx.Request) -> httpx.Response:
        if "brokenco" in str(request.url):
            return httpx.Response(500)
        lever_payload = json.loads((FIXTURES / "lever_sample.json").read_text())
        return httpx.Response(200, json=lever_payload)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    companies = [
        CompanyBoardConfig(name="Broken Co", board_type="greenhouse", board_slug="brokenco"),
        CompanyBoardConfig(name="Zoox", board_type="lever", board_slug="zoox"),
    ]
    adapter = JobBoardAdapter(companies=companies, client=client)
    postings = adapter.fetch()
    assert len(postings) == 2  # only Zoox's postings, Broken Co's 500 was skipped
    assert all(p.company == "Zoox" for p in postings)
