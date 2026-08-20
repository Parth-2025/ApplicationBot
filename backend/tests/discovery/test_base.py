from datetime import date
from discovery.adapters.base import RawPosting


def test_raw_posting_defaults():
    posting = RawPosting(
        company="Acme",
        role_title="SWE Intern",
        source="test_source",
        source_url="https://example.com/jobs/1",
    )
    assert posting.location is None
    assert posting.raw_description is None
    assert posting.posted_date is None


def test_raw_posting_all_fields():
    posting = RawPosting(
        company="Acme",
        role_title="SWE Intern",
        source="test_source",
        source_url="https://example.com/jobs/1",
        location="Remote",
        raw_description="Build things.",
        posted_date=date(2026, 8, 20),
    )
    assert posting.location == "Remote"
    assert posting.raw_description == "Build things."
    assert posting.posted_date == date(2026, 8, 20)
