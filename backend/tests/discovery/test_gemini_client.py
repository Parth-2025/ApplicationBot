import time

import pytest
from discovery.gemini_client import GeminiClient, GeminiError, GeminiQuotaExhaustedError


class FakeResponse:
    def __init__(self, text):
        self.text = text


class FakeModel:
    def __init__(self, responses):
        self._responses = list(responses)
        self.calls = 0
        self.call_times: list[float] = []
        self.last_request_options = None

    def generate_content(self, prompt, request_options=None):
        self.calls += 1
        self.call_times.append(time.monotonic())
        self.last_request_options = request_options
        response = self._responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return FakeResponse(response)


def test_generate_json_parses_plain_json():
    model = FakeModel(['{"a": 1, "b": true}'])
    client = GeminiClient(model=model, min_seconds_between_calls=0)
    assert client.generate_json("prompt") == {"a": 1, "b": True}


def test_generate_json_strips_markdown_fence():
    model = FakeModel(['```json\n{"a": 1}\n```'])
    client = GeminiClient(model=model, min_seconds_between_calls=0)
    assert client.generate_json("prompt") == {"a": 1}


def test_generate_json_retries_then_succeeds():
    model = FakeModel([RuntimeError("boom"), '{"a": 1}'])
    client = GeminiClient(model=model, min_seconds_between_calls=0)
    result = client.generate_json("prompt", retries=1)
    assert result == {"a": 1}
    assert model.calls == 2


def test_generate_json_raises_gemini_error_after_exhausting_retries():
    model = FakeModel([RuntimeError("boom"), RuntimeError("boom again")])
    client = GeminiClient(model=model, min_seconds_between_calls=0)
    with pytest.raises(GeminiError):
        client.generate_json("prompt", retries=1)
    assert model.calls == 2


def test_generate_json_raises_gemini_error_on_invalid_json():
    model = FakeModel(["not json at all"])
    client = GeminiClient(model=model, min_seconds_between_calls=0)
    with pytest.raises(GeminiError):
        client.generate_json("prompt", retries=0)


def test_generate_content_called_with_request_timeout():
    model = FakeModel(['{"a": 1}'])
    client = GeminiClient(model=model, request_timeout=15.0, min_seconds_between_calls=0)
    client.generate_json("prompt")
    assert model.last_request_options == {"timeout": 15.0}


def test_generate_content_uses_default_request_timeout():
    model = FakeModel(['{"a": 1}'])
    client = GeminiClient(model=model, min_seconds_between_calls=0)
    client.generate_json("prompt")
    assert model.last_request_options == {"timeout": 30.0}


class HangingModel:
    """Simulates the SDK not honoring its own request_options timeout."""

    def generate_content(self, prompt, request_options=None):
        time.sleep(5)
        return FakeResponse('{"a": 1}')


def test_hard_deadline_terminates_call_that_ignores_sdk_timeout():
    model = HangingModel()
    client = GeminiClient(model=model, request_timeout=0.2, min_seconds_between_calls=0)
    start = time.monotonic()
    with pytest.raises(GeminiError):
        client.generate_json("prompt", retries=0)
    elapsed = time.monotonic() - start
    assert elapsed < 2.0  # bounded by request_timeout, not the model's 5s sleep


def test_rate_limit_paces_successive_calls():
    model = FakeModel(['{"a": 1}', '{"a": 2}'])
    client = GeminiClient(model=model, min_seconds_between_calls=0.3)
    client.generate_json("prompt")
    client.generate_json("prompt")
    assert len(model.call_times) == 2
    assert model.call_times[1] - model.call_times[0] >= 0.3


def test_daily_quota_exhaustion_raises_specific_error_without_retrying():
    quota_error = RuntimeError(
        "429 quota exceeded ... GenerateRequestsPerDayPerProjectPerModel-FreeTier ..."
    )
    model = FakeModel([quota_error])
    client = GeminiClient(model=model, min_seconds_between_calls=0)
    with pytest.raises(GeminiQuotaExhaustedError):
        client.generate_json("prompt", retries=3)
    assert model.calls == 1  # no retry attempted - retrying a daily cap is pointless


def test_per_minute_quota_error_still_retries_normally():
    minute_error = RuntimeError(
        "429 quota exceeded ... GenerateRequestsPerMinutePerProjectPerModel-FreeTier ..."
    )
    model = FakeModel([minute_error, '{"a": 1}'])
    client = GeminiClient(model=model, min_seconds_between_calls=0)
    result = client.generate_json("prompt", retries=1)
    assert result == {"a": 1}
    assert model.calls == 2
