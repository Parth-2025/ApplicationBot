import pytest
from discovery.adapters.base import RawPosting
from discovery.classifier import classify_posting, classify_postings_batch
from discovery.gemini_client import GeminiError, GeminiQuotaExhaustedError


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


def test_classify_posting_passes_when_role_and_term_match():
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
    assert result.still_open is True
    assert result.us_based is True


def test_classify_posting_passes_but_records_not_open():
    # Only role category + Summer 2027 term are hard filters - still_open
    # is recorded as data, not used to exclude the posting.
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
    assert result.passed is True
    assert result.still_open is False


def test_classify_posting_passes_but_records_senior_only_eligibility():
    # eligibility is recorded as data, not used to exclude the posting.
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
    assert result.passed is True
    assert result.eligibility == "senior_only"


def test_classify_posting_passes_but_records_unpaid_and_non_us():
    # paid and US-based are recorded as data, not used to exclude the posting.
    client = FakeGeminiClient(
        {
            "still_open": True,
            "is_summer_2027": True,
            "is_paid": False,
            "is_us_based": False,
            "eligibility": "all_levels",
            "role_category": "swe_ai_ml",
        }
    )
    result = classify_posting(client, _posting())
    assert result.passed is True
    assert result.paid is False
    assert result.us_based is False


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


def test_classify_posting_fails_when_not_summer_2027():
    client = FakeGeminiClient(
        {
            "still_open": True,
            "is_summer_2027": False,
            "is_paid": True,
            "is_us_based": True,
            "eligibility": "all_levels",
            "role_category": "swe_ai_ml",
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


def _passing_entry(**overrides):
    entry = {
        "still_open": True,
        "is_summer_2027": True,
        "is_paid": True,
        "is_us_based": True,
        "eligibility": "soph_junior",
        "role_category": "swe_ai_ml",
    }
    entry.update(overrides)
    return entry


def test_classify_postings_batch_returns_empty_list_for_no_postings():
    client = FakeGeminiClient([])
    assert classify_postings_batch(client, []) == []


def test_classify_postings_batch_maps_results_in_order():
    client = FakeGeminiClient(
        [
            _passing_entry(),
            _passing_entry(is_summer_2027=False),
            _passing_entry(role_category="other"),
        ]
    )
    postings = [
        _posting(company="Alpha", source_url="https://example.com/1"),
        _posting(company="Beta", source_url="https://example.com/2"),
        _posting(company="Gamma", source_url="https://example.com/3"),
    ]
    results = classify_postings_batch(client, postings)
    assert len(results) == 3
    assert results[0].passed is True
    assert results[1].passed is False
    assert results[2].passed is False


def test_classify_postings_batch_includes_all_postings_in_prompt():
    client = FakeGeminiClient([_passing_entry(), _passing_entry()])
    postings = [
        _posting(company="UniqueCo1", role_title="Role One", source_url="https://example.com/1"),
        _posting(company="UniqueCo2", role_title="Role Two", source_url="https://example.com/2"),
    ]
    classify_postings_batch(client, postings)
    assert "UniqueCo1" in client.last_prompt
    assert "Role One" in client.last_prompt
    assert "UniqueCo2" in client.last_prompt
    assert "Role Two" in client.last_prompt


def test_classify_postings_batch_returns_all_none_on_gemini_failure():
    client = FakeGeminiClient(GeminiError("boom"))
    postings = [_posting(source_url="https://example.com/1"), _posting(source_url="https://example.com/2")]
    results = classify_postings_batch(client, postings)
    assert results == [None, None]


def test_classify_postings_batch_returns_all_none_when_response_is_not_a_list():
    client = FakeGeminiClient({"not": "a list"})
    postings = [_posting(source_url="https://example.com/1")]
    results = classify_postings_batch(client, postings)
    assert results == [None]


def test_classify_postings_batch_handles_malformed_entry_without_crashing():
    client = FakeGeminiClient([_passing_entry(), "not a dict", _passing_entry()])
    postings = [
        _posting(source_url="https://example.com/1"),
        _posting(source_url="https://example.com/2"),
        _posting(source_url="https://example.com/3"),
    ]
    results = classify_postings_batch(client, postings)
    assert results[0].passed is True
    assert results[1] is None
    assert results[2].passed is True


def test_classify_postings_batch_handles_fewer_results_than_postings():
    client = FakeGeminiClient([_passing_entry()])
    postings = [
        _posting(source_url="https://example.com/1"),
        _posting(source_url="https://example.com/2"),
    ]
    results = classify_postings_batch(client, postings)
    assert results[0].passed is True
    assert results[1] is None


def test_classify_postings_batch_propagates_quota_exhausted_error():
    client = FakeGeminiClient(GeminiQuotaExhaustedError("daily quota exhausted"))
    postings = [_posting(source_url="https://example.com/1")]
    with pytest.raises(GeminiQuotaExhaustedError):
        classify_postings_batch(client, postings)
