# backend/tests/discovery/test_pipeline.py
from datetime import date

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app import crud, schemas
from app.database import Base
from app.models import Eligibility, JobStatus
from discovery.adapters.base import RawPosting
from discovery.classifier import ClassificationResult
from discovery.pipeline import run_discovery


@pytest.fixture()
def db_session_factory():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)
    return TestingSessionLocal


class FakeAdapter:
    def __init__(self, postings=None, error=None):
        self._postings = postings or []
        self._error = error

    def fetch(self):
        if self._error:
            raise self._error
        return self._postings


class FakeClassifierClient:
    """Stands in for the Gemini client passed to classify_posting."""

    def __init__(self, results_by_role_title: dict):
        self.results_by_role_title = results_by_role_title

    def generate_json(self, prompt, retries=1):
        for role_title, result in self.results_by_role_title.items():
            if role_title in prompt:
                if isinstance(result, Exception):
                    raise result
                return result
        raise AssertionError(f"No fake classifier result configured for prompt: {prompt[:200]}")


def _posting(**overrides):
    defaults = dict(
        company="Acme",
        role_title="AI Engineering Intern",
        source="test_source",
        source_url="https://example.com/jobs/1",
        location="Remote",
        raw_description="Summer 2027 AI internship open to sophomores and juniors.",
    )
    defaults.update(overrides)
    return RawPosting(**defaults)


def _passing_result():
    return {
        "still_open": True,
        "is_summer_2027": True,
        "is_paid": True,
        "is_us_based": True,
        "eligibility": "soph_junior",
        "role_category": "swe_ai_ml",
    }


def test_writes_postings_that_pass_classification(db_session_factory):
    adapter = FakeAdapter(postings=[_posting()])
    client = FakeClassifierClient({"AI Engineering Intern": _passing_result()})

    summary = run_discovery(
        adapters=[adapter], classifier_client=client, db_session_factory=db_session_factory,
        sleep_between_gemini_calls=0,
    )

    assert summary.found == 1
    assert summary.passed_filter == 1
    assert summary.written == 1

    db = db_session_factory()
    jobs = crud.list_jobs(db)
    assert len(jobs) == 1
    assert jobs[0].company == "Acme"
    assert jobs[0].status == JobStatus.new
    assert jobs[0].eligibility == Eligibility.soph_junior


def test_skips_postings_that_fail_classification(db_session_factory):
    # Only role category + Summer 2027 term are hard filters now.
    adapter = FakeAdapter(postings=[_posting()])
    failing_result = {**_passing_result(), "role_category": "other"}
    client = FakeClassifierClient({"AI Engineering Intern": failing_result})

    summary = run_discovery(
        adapters=[adapter], classifier_client=client, db_session_factory=db_session_factory,
        sleep_between_gemini_calls=0,
    )

    assert summary.found == 1
    assert summary.passed_filter == 0
    assert summary.written == 0

    db = db_session_factory()
    assert crud.list_jobs(db) == []


def test_writes_posting_with_unpaid_non_us_not_open_but_recorded_as_data(db_session_factory):
    # paid/us_based/still_open/eligibility no longer gate whether a posting
    # is written - they're recorded as data on the job.
    adapter = FakeAdapter(postings=[_posting()])
    result = {
        **_passing_result(),
        "is_paid": False,
        "is_us_based": False,
        "still_open": False,
        "eligibility": "senior_only",
    }
    client = FakeClassifierClient({"AI Engineering Intern": result})

    summary = run_discovery(
        adapters=[adapter], classifier_client=client, db_session_factory=db_session_factory,
        sleep_between_gemini_calls=0,
    )

    assert summary.written == 1

    db = db_session_factory()
    jobs = crud.list_jobs(db)
    assert len(jobs) == 1
    assert jobs[0].paid is False
    assert jobs[0].us_based is False
    assert jobs[0].still_open is False
    assert jobs[0].eligibility == Eligibility.senior_only


def test_one_adapter_failing_does_not_stop_others(db_session_factory):
    broken_adapter = FakeAdapter(error=RuntimeError("source down"))
    working_adapter = FakeAdapter(postings=[_posting()])
    client = FakeClassifierClient({"AI Engineering Intern": _passing_result()})

    summary = run_discovery(
        adapters=[broken_adapter, working_adapter],
        classifier_client=client,
        db_session_factory=db_session_factory,
        sleep_between_gemini_calls=0,
    )

    assert summary.written == 1
    assert len(summary.errors) == 1
    assert "source down" in summary.errors[0]


def test_fuzzy_duplicate_from_different_source_is_skipped(db_session_factory):
    db = db_session_factory()
    crud.create_or_update_job(
        db,
        schemas.JobCreate(
            company="Acme",
            role_title="AI Engineering Intern",
            source="simplifyjobs_github",
            source_url="https://github-list.example.com/acme-ai-intern",
            discovered_date=date.today(),
            eligibility=Eligibility.soph_junior,
        ),
    )

    adapter = FakeAdapter(
        postings=[
            _posting(
                company="Acme",
                role_title="AI Engineering Intern",  # same company+role, different source_url
                source="greenhouse",
                source_url="https://boards.greenhouse.io/acme/jobs/1",
            )
        ]
    )
    client = FakeClassifierClient({"AI Engineering Intern": _passing_result()})

    summary = run_discovery(
        adapters=[adapter], classifier_client=client, db_session_factory=db_session_factory,
        sleep_between_gemini_calls=0,
    )

    assert summary.passed_filter == 1
    assert summary.written == 0  # duplicate, not written again

    jobs = crud.list_jobs(db_session_factory())
    assert len(jobs) == 1  # still just the original


def test_gemini_classification_failure_is_skipped_not_counted_as_error(db_session_factory):
    from discovery.gemini_client import GeminiError

    adapter = FakeAdapter(postings=[_posting()])
    client = FakeClassifierClient({"AI Engineering Intern": GeminiError("boom")})

    summary = run_discovery(
        adapters=[adapter], classifier_client=client, db_session_factory=db_session_factory,
        sleep_between_gemini_calls=0,
    )

    assert summary.found == 1
    assert summary.passed_filter == 0
    assert summary.written == 0
    assert summary.errors == []


def test_concurrent_classification_keeps_results_matched_to_their_posting(db_session_factory):
    # Classification runs on a thread pool for speed - verify each posting
    # still ends up written under its own correct company/role, not mixed
    # up with another posting's result under concurrency. Company/role
    # names must be genuinely distinct (not near-duplicates of each other)
    # so the fuzzy-dedup check doesn't collapse them into one write.
    companies = [
        "Alpha Robotics", "Beacon Systems", "Cobalt Analytics", "Driftwood Labs",
        "Everline Health", "Fjordly Games", "Granite Freight", "Hollow Point Security",
        "Ironclad Finance", "Jubilee Media",
    ]
    postings = [
        _posting(
            company=companies[i],
            role_title=f"AI Engineering Intern - Team {companies[i]}",
            source_url=f"https://example.com/jobs/{i}",
        )
        for i in range(10)
    ]
    adapter = FakeAdapter(postings=postings)
    client = FakeClassifierClient(
        {f"Team {companies[i]}": _passing_result() for i in range(10)}
    )

    summary = run_discovery(
        adapters=[adapter],
        classifier_client=client,
        db_session_factory=db_session_factory,
        sleep_between_gemini_calls=0,
        max_concurrent_classifications=5,
    )

    assert summary.found == 10
    assert summary.written == 10

    jobs = crud.list_jobs(db_session_factory())
    assert len(jobs) == 10
    for company in companies:
        matching = [j for j in jobs if j.company == company]
        assert len(matching) == 1
        assert matching[0].role_title == f"AI Engineering Intern - Team {company}"
