# backend/tests/test_crud.py
from datetime import date
import pytest
from app import crud, schemas
from app.models import JobStatus, Eligibility


def make_job_in(**overrides):
    defaults = dict(
        company="Acme",
        role_title="AI Engineering Intern",
        source="simplify",
        source_url="https://example.com/acme-ai-intern",
        discovered_date=date(2026, 8, 19),
        eligibility=Eligibility.soph_junior,
    )
    defaults.update(overrides)
    return schemas.JobCreate(**defaults)


def test_create_or_update_job_creates_new(db_session):
    job = crud.create_or_update_job(db_session, make_job_in())
    assert job.id is not None
    assert job.status == JobStatus.new


def test_create_or_update_job_upserts_existing(db_session):
    first = crud.create_or_update_job(db_session, make_job_in())
    second = crud.create_or_update_job(
        db_session, make_job_in(discovered_date=date(2026, 8, 20))
    )
    assert second.id == first.id
    all_jobs = crud.list_jobs(db_session)
    assert len(all_jobs) == 1
    assert all_jobs[0].discovered_date == date(2026, 8, 20)


def test_update_job_status_valid_transition(db_session):
    job = crud.create_or_update_job(db_session, make_job_in())
    updated = crud.update_job_status(db_session, job, JobStatus.tailored)
    assert updated.status == JobStatus.tailored


def test_update_job_status_invalid_transition_raises(db_session):
    job = crud.create_or_update_job(db_session, make_job_in())
    with pytest.raises(crud.InvalidStatusTransition):
        crud.update_job_status(db_session, job, JobStatus.applied)


def test_mark_applied_creates_application_record(db_session):
    job = crud.create_or_update_job(db_session, make_job_in())
    crud.update_job_status(db_session, job, JobStatus.tailored)

    updated = crud.mark_applied(
        db_session,
        job,
        applied_date=date(2026, 8, 21),
        application_number="APP-123",
        notes="Referred by a friend",
    )
    assert updated.status == JobStatus.applied
    assert len(updated.applications) == 1
    assert updated.applications[0].applied_date == date(2026, 8, 21)
    assert updated.applications[0].application_number == "APP-123"
