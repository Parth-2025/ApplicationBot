# backend/tests/test_tailoring.py
from app.models import Job
from app.tailoring import generate_tailored_resume


class FakeGeminiClient:
    def __init__(self, response_text):
        self.response_text = response_text
        self.last_prompt = None

    def generate_text(self, prompt, retries=1):
        self.last_prompt = prompt
        return self.response_text


def _job(**overrides):
    defaults = dict(
        company="Acme",
        role_title="AI Engineering Intern",
        source="simplify",
        source_url="https://example.com/acme-ai",
        raw_job_description="Build and evaluate LLM-powered features for our platform.",
    )
    defaults.update(overrides)
    return Job(**defaults)


def test_generate_tailored_resume_returns_client_response():
    client = FakeGeminiClient("Tailored resume text.")
    result = generate_tailored_resume(client, "Master resume content", _job())
    assert result == "Tailored resume text."


def test_prompt_includes_master_resume_and_job_details():
    client = FakeGeminiClient("ignored")
    generate_tailored_resume(client, "MASTER_RESUME_MARKER", _job())

    assert "MASTER_RESUME_MARKER" in client.last_prompt
    assert "Acme" in client.last_prompt
    assert "AI Engineering Intern" in client.last_prompt
    assert "Build and evaluate LLM-powered features" in client.last_prompt


def test_prompt_enforces_same_structure_and_single_page_constraints():
    client = FakeGeminiClient("ignored")
    generate_tailored_resume(client, "Master resume content", _job())

    prompt_lower = client.last_prompt.lower()
    assert "same number of bullet" in prompt_lower
    assert "single page" in prompt_lower
    assert "do not invent" in prompt_lower


def test_prompt_handles_missing_job_description():
    client = FakeGeminiClient("ignored")
    generate_tailored_resume(
        client, "Master resume content", _job(raw_job_description=None)
    )
    assert "no description available" in client.last_prompt.lower()
