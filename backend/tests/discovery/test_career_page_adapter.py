import httpx

from discovery.adapters.career_page import CareerPageAdapter
from discovery.config import CareerPageConfig
from discovery.gemini_client import GeminiError


class FakeGeminiClient:
    def __init__(self, responses):
        self._responses = list(responses)
        self.prompts = []

    def generate_json(self, prompt, retries=1):
        self.prompts.append(prompt)
        result = self._responses.pop(0)
        if isinstance(result, Exception):
            raise result
        return result


def _page_client(html_by_url: dict):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text=html_by_url.get(str(request.url), "<html></html>"))

    return httpx.Client(transport=httpx.MockTransport(handler))


def test_extracts_multiple_postings_from_one_page():
    page_client = _page_client(
        {"https://acme.example.com/careers": "<html><body>AI Intern, SWE Intern listings...</body></html>"}
    )
    gemini = FakeGeminiClient(
        [
            [
                {
                    "role_title": "AI Engineering Intern",
                    "location": "Remote",
                    "description": "Summer 2027 AI internship.",
                    "url": "https://acme.example.com/careers/ai-intern",
                },
                {
                    "role_title": "SWE Intern",
                    "location": "New York, NY",
                    "description": "Summer 2027 software engineering internship.",
                    "url": "https://acme.example.com/careers/swe-intern",
                },
            ]
        ]
    )
    adapter = CareerPageAdapter(
        pages=[CareerPageConfig(name="Acme", url="https://acme.example.com/careers")],
        gemini_client=gemini,
        client=page_client,
    )
    postings = adapter.fetch()

    assert len(postings) == 2
    assert all(p.company == "Acme" for p in postings)
    assert all(p.source == "career_page" for p in postings)
    titles = {p.role_title for p in postings}
    assert titles == {"AI Engineering Intern", "SWE Intern"}


def test_empty_extraction_returns_no_postings():
    page_client = _page_client({"https://emptyco.example.com/careers": "<html></html>"})
    gemini = FakeGeminiClient([[]])
    adapter = CareerPageAdapter(
        pages=[CareerPageConfig(name="EmptyCo", url="https://emptyco.example.com/careers")],
        gemini_client=gemini,
        client=page_client,
    )
    postings = adapter.fetch()
    assert postings == []


def test_gemini_failure_skips_that_page_but_not_others():
    page_client = _page_client(
        {
            "https://brokenco.example.com/careers": "<html>broken</html>",
            "https://goodco.example.com/careers": "<html>good</html>",
        }
    )
    gemini = FakeGeminiClient(
        [
            GeminiError("boom"),
            [
                {
                    "role_title": "SWE Intern",
                    "location": "Remote",
                    "description": "desc",
                    "url": "https://goodco.example.com/careers/swe",
                }
            ],
        ]
    )
    adapter = CareerPageAdapter(
        pages=[
            CareerPageConfig(name="Broken Co", url="https://brokenco.example.com/careers"),
            CareerPageConfig(name="Good Co", url="https://goodco.example.com/careers"),
        ],
        gemini_client=gemini,
        client=page_client,
    )
    postings = adapter.fetch()
    assert len(postings) == 1
    assert postings[0].company == "Good Co"


def test_page_fetch_failure_skips_that_page():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    gemini = FakeGeminiClient([])
    adapter = CareerPageAdapter(
        pages=[CareerPageConfig(name="DownCo", url="https://downco.example.com/careers")],
        gemini_client=gemini,
        client=client,
    )
    postings = adapter.fetch()
    assert postings == []


def test_malformed_entry_is_skipped_but_valid_entry_still_returned():
    page_client = _page_client(
        {"https://mixedco.example.com/careers": "<html><body>listings...</body></html>"}
    )
    gemini = FakeGeminiClient(
        [
            [
                {
                    # missing "role_title" entirely - schema drift/hallucination
                    "location": "Remote",
                    "description": "Missing role title.",
                    "url": "https://mixedco.example.com/careers/bad",
                },
                {
                    "role_title": "SWE Intern",
                    "location": "Austin, TX",
                    "description": "Summer 2027 software engineering internship.",
                    "url": "https://mixedco.example.com/careers/swe-intern",
                },
            ]
        ]
    )
    adapter = CareerPageAdapter(
        pages=[CareerPageConfig(name="MixedCo", url="https://mixedco.example.com/careers")],
        gemini_client=gemini,
        client=page_client,
    )
    postings = adapter.fetch()

    assert len(postings) == 1
    assert postings[0].role_title == "SWE Intern"
    assert postings[0].company == "MixedCo"
