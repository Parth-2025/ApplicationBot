import httpx

from discovery.adapters.web_search import WebSearchAdapter
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


def _search_client(items):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"items": items})

    return httpx.Client(transport=httpx.MockTransport(handler))


def _page_client(html_by_url: dict):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text=html_by_url.get(str(request.url), "<html></html>"))

    return httpx.Client(transport=httpx.MockTransport(handler))


def test_extracts_posting_from_search_result_page():
    search_client = _search_client(
        [{"title": "AI Intern - Acme", "link": "https://acme.example.com/jobs/1", "snippet": "..."}]
    )
    page_client = _page_client(
        {"https://acme.example.com/jobs/1": "<html><body>AI Engineering Intern at Acme, Summer 2027</body></html>"}
    )
    gemini = FakeGeminiClient(
        [
            {
                "is_job_posting": True,
                "company": "Acme",
                "role_title": "AI Engineering Intern",
                "location": "Remote",
                "description": "AI Engineering Intern at Acme, Summer 2027",
            }
        ]
    )
    adapter = WebSearchAdapter(
        queries=["AI engineering intern Summer 2027"],
        google_api_key="key",
        google_cx="cx",
        gemini_client=gemini,
        search_client=search_client,
        page_client=page_client,
    )
    postings = adapter.fetch()

    assert len(postings) == 1
    posting = postings[0]
    assert posting.company == "Acme"
    assert posting.role_title == "AI Engineering Intern"
    assert posting.source == "google_search"
    assert posting.source_url == "https://acme.example.com/jobs/1"
    assert posting.location == "Remote"


def test_skips_result_gemini_says_is_not_a_posting():
    search_client = _search_client(
        [{"title": "Careers at Acme", "link": "https://acme.example.com/careers", "snippet": "..."}]
    )
    page_client = _page_client({"https://acme.example.com/careers": "<html><body>See all our jobs</body></html>"})
    gemini = FakeGeminiClient([{"is_job_posting": False}])
    adapter = WebSearchAdapter(
        queries=["AI engineering intern Summer 2027"],
        google_api_key="key",
        google_cx="cx",
        gemini_client=gemini,
        search_client=search_client,
        page_client=page_client,
    )
    postings = adapter.fetch()
    assert postings == []


def test_skips_result_on_gemini_failure():
    search_client = _search_client(
        [{"title": "AI Intern - Acme", "link": "https://acme.example.com/jobs/1", "snippet": "..."}]
    )
    page_client = _page_client({"https://acme.example.com/jobs/1": "<html><body>content</body></html>"})
    gemini = FakeGeminiClient([GeminiError("boom")])
    adapter = WebSearchAdapter(
        queries=["AI engineering intern Summer 2027"],
        google_api_key="key",
        google_cx="cx",
        gemini_client=gemini,
        search_client=search_client,
        page_client=page_client,
    )
    postings = adapter.fetch()
    assert postings == []


def test_skips_result_when_gemini_output_missing_required_fields():
    search_client = _search_client(
        [{"title": "AI Intern - Acme", "link": "https://acme.example.com/jobs/1", "snippet": "..."}]
    )
    page_client = _page_client({"https://acme.example.com/jobs/1": "<html><body>content</body></html>"})
    gemini = FakeGeminiClient([{"is_job_posting": True}])
    adapter = WebSearchAdapter(
        queries=["AI engineering intern Summer 2027"],
        google_api_key="key",
        google_cx="cx",
        gemini_client=gemini,
        search_client=search_client,
        page_client=page_client,
    )
    postings = adapter.fetch()
    assert postings == []


def test_search_failure_for_one_query_does_not_abort_other_queries():
    def handler(request: httpx.Request) -> httpx.Response:
        query = request.url.params.get("q")
        if query == "bad query":
            return httpx.Response(429, json={"error": "rate limited"})
        return httpx.Response(
            200,
            json={
                "items": [
                    {"title": "AI Intern - Acme", "link": "https://acme.example.com/jobs/1", "snippet": "..."}
                ]
            },
        )

    search_client = httpx.Client(transport=httpx.MockTransport(handler))
    page_client = _page_client(
        {"https://acme.example.com/jobs/1": "<html><body>AI Engineering Intern at Acme</body></html>"}
    )
    gemini = FakeGeminiClient(
        [
            {
                "is_job_posting": True,
                "company": "Acme",
                "role_title": "AI Engineering Intern",
                "location": "Remote",
                "description": "AI Engineering Intern at Acme",
            }
        ]
    )
    adapter = WebSearchAdapter(
        queries=["bad query", "good query"],
        google_api_key="key",
        google_cx="cx",
        gemini_client=gemini,
        search_client=search_client,
        page_client=page_client,
    )
    postings = adapter.fetch()

    assert len(postings) == 1
    assert postings[0].company == "Acme"


def test_respects_max_results_per_query():
    items = [
        {"title": f"Result {i}", "link": f"https://example.com/{i}", "snippet": "..."} for i in range(10)
    ]
    search_client = _search_client(items)
    page_client = _page_client({})
    gemini = FakeGeminiClient([{"is_job_posting": False}] * 3)
    adapter = WebSearchAdapter(
        queries=["some query"],
        google_api_key="key",
        google_cx="cx",
        gemini_client=gemini,
        search_client=search_client,
        page_client=page_client,
        max_results_per_query=3,
    )
    adapter.fetch()
    assert len(gemini.prompts) == 3
