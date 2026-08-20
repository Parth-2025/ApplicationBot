from discovery.adapters.base import RawPosting
from discovery.classifier import classify_posting
from discovery.gemini_client import GeminiError


class FakeGeminiClient:
    def __init__(self, result):
        self.result = result
        self.last_prompt = None

    def generate_json(self, prompt, retries=1):
        self.last_prompt = prompt
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


def _posting(**overrides):
    defaults = dict(
        company="Acme",
        role_title="AI Engineering Intern",
        source="test",
        source_url="https://example.com/jobs/1",
        location="San Francisco, CA",
        raw_description="Join our AI team as a Summer 2027 intern open to sophomores and juniors.",
    )
    defaults.update(overrides)
    return RawPosting(**defaults)


def test_classify_posting_passes_when_all_criteria_met():
    client = FakeGeminiClient(
        {
            "still_open": True,
            "is_summer_2027": True,
            "is_paid": True,
            "is_us_based": True,
            "eligibility": "soph_junior",
            "role_category": "swe_ai_ml",
        }
    )
    result = classify_posting(client, _posting())
    assert result.passed is True
    assert result.eligibility == "soph_junior"
    assert result.paid is True


def test_classify_posting_fails_when_not_open():
    client = FakeGeminiClient(
        {
            "still_open": False,
            "is_summer_2027": True,
            "is_paid": True,
            "is_us_based": True,
            "eligibility": "soph_junior",
            "role_category": "swe_ai_ml",
        }
    )
    result = classify_posting(client, _posting())
    assert result.passed is False


def test_classify_posting_fails_when_senior_only():
    client = FakeGeminiClient(
        {
            "still_open": True,
            "is_summer_2027": True,
            "is_paid": True,
            "is_us_based": True,
            "eligibility": "senior_only",
            "role_category": "swe_ai_ml",
        }
    )
    result = classify_posting(client, _posting())
    assert result.passed is False
    assert result.eligibility == "senior_only"


def test_classify_posting_fails_when_wrong_role_category():
    client = FakeGeminiClient(
        {
            "still_open": True,
            "is_summer_2027": True,
            "is_paid": True,
            "is_us_based": True,
            "eligibility": "all_levels",
            "role_category": "other",
        }
    )
    result = classify_posting(client, _posting())
    assert result.passed is False


def test_classify_posting_returns_none_on_gemini_failure():
    client = FakeGeminiClient(GeminiError("boom"))
    result = classify_posting(client, _posting())
    assert result is None


def test_classify_posting_includes_posting_fields_in_prompt():
    client = FakeGeminiClient(
        {
            "still_open": True,
            "is_summer_2027": True,
            "is_paid": True,
            "is_us_based": True,
            "eligibility": "all_levels",
            "role_category": "swe_ai_ml",
        }
    )
    classify_posting(client, _posting(company="UniqueCo", role_title="Unique Role Title"))
    assert "UniqueCo" in client.last_prompt
    assert "Unique Role Title" in client.last_prompt
