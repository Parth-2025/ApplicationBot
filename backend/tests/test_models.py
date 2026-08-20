# backend/tests/test_models.py
from datetime import date
import pytest
from sqlalchemy.exc import IntegrityError
from app.models import Job, Eligibility, JobStatus


def test_create_job(db_session):
    job = Job(
        company="Acme",
        role_title="AI Engineering Intern",
        source="simplify",
        source_url="https://example.com/acme-ai-intern",
        location="Remote",
        paid=True,
        eligibility=Eligibility.soph_junior,
        discovered_date=date(2026, 8, 19),
        status=JobStatus.new,
    )
    db_session.add(job)
    db_session.commit()

    fetched = db_session.query(Job).first()
    assert fetched.company == "Acme"
    assert fetched.status == JobStatus.new
    assert fetched.eligibility == Eligibility.soph_junior


def test_duplicate_job_identity_rejected(db_session):
    kwargs = dict(
        company="Acme",
        role_title="AI Engineering Intern",
        source="simplify",
        source_url="https://example.com/acme-ai-intern",
        discovered_date=date(2026, 8, 19),
    )
    db_session.add(Job(**kwargs))
    db_session.commit()

    db_session.add(Job(**kwargs))
    with pytest.raises(IntegrityError):
        db_session.commit()
