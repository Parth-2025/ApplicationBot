import time

import pytest
from discovery.gemini_client import GeminiClient, GeminiError


class FakeResponse:
    def __init__(self, text):
        self.text = text


class FakeModel:
    def __init__(self, responses):
        self._responses = list(responses)
        self.calls = 0
        self.last_request_options = None

    def generate_content(self, prompt, request_options=None):
        self.calls += 1
        self.last_request_options = request_options
        response = self._responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return FakeResponse(response)


def test_generate_json_parses_plain_json():
    model = FakeModel(['{"a": 1, "b": true}'])
    client = GeminiClient(model=model)
    assert client.generate_json("prompt") == {"a": 1, "b": True}


def test_generate_json_strips_markdown_fence():
    model = FakeModel(['```json\n{"a": 1}\n```'])
    client = GeminiClient(model=model)
    assert client.generate_json("prompt") == {"a": 1}


def test_generate_json_retries_then_succeeds():
    model = FakeModel([RuntimeError("boom"), '{"a": 1}'])
    client = GeminiClient(model=model)
    result = client.generate_json("prompt", retries=1)
    assert result == {"a": 1}
    assert model.calls == 2


def test_generate_json_raises_gemini_error_after_exhausting_retries():
    model = FakeModel([RuntimeError("boom"), RuntimeError("boom again")])
    client = GeminiClient(model=model)
    with pytest.raises(GeminiError):
        client.generate_json("prompt", retries=1)
    assert model.calls == 2


def test_generate_json_raises_gemini_error_on_invalid_json():
    model = FakeModel(["not json at all"])
    client = GeminiClient(model=model)
    with pytest.raises(GeminiError):
        client.generate_json("prompt", retries=0)


def test_generate_content_called_with_request_timeout():
    model = FakeModel(['{"a": 1}'])
    client = GeminiClient(model=model, request_timeout=15.0)
    client.generate_json("prompt")
    assert model.last_request_options == {"timeout": 15.0}


def test_generate_content_uses_default_request_timeout():
    model = FakeModel(['{"a": 1}'])
    client = GeminiClient(model=model)
    client.generate_json("prompt")
    assert model.last_request_options == {"timeout": 30.0}


class HangingModel:
    """Simulates the SDK not honoring its own request_options timeout."""

    def generate_content(self, prompt, request_options=None):
        time.sleep(5)
        return FakeResponse('{"a": 1}')


def test_hard_deadline_terminates_call_that_ignores_sdk_timeout():
    model = HangingModel()
    client = GeminiClient(model=model, request_timeout=0.2)
    start = time.monotonic()
    with pytest.raises(GeminiError):
        client.generate_json("prompt", retries=0)
    elapsed = time.monotonic() - start
    assert elapsed < 2.0  # bounded by request_timeout, not the model's 5s sleep
