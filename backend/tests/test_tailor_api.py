# backend/tests/test_tailor_api.py
from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.main import app
from app.database import Base, get_db
from app import crud, schemas
from app.models import Eligibility, JobStatus
from app.routers.jobs import get_gemini_client
from discovery.gemini_client import GeminiError


class FakeGeminiClient:
    def __init__(self, text_or_error):
        self._text_or_error = text_or_error
        self.last_prompt = None

    def generate_text(self, prompt, retries=1):
        self.last_prompt = prompt
        if isinstance(self._text_or_error, Exception):
            raise self._text_or_error
        return self._text_or_error


@pytest.fixture()
def client_factory():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)

    def override_get_db():
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db

    def _make(gemini_client):
        app.dependency_overrides[get_gemini_client] = lambda: gemini_client
        return TestClient(app), TestingSessionLocal

    yield _make
    app.dependency_overrides.clear()


def _make_job(SessionLocal):
    db = SessionLocal()
    job = crud.create_or_update_job(
        db,
        schemas.JobCreate(
            company="Acme",
            role_title="AI Engineering Intern",
            source="simplify",
            source_url="https://example.com/acme-ai",
            discovered_date=date(2026, 8, 19),
            eligibility=Eligibility.soph_junior,
            raw_job_description="Build AI features.",
        ),
    )
    db.close()
    return job


def test_generate_returns_404_when_no_master_resume(client_factory):
    test_client, SessionLocal = client_factory(FakeGeminiClient("draft text"))
    job = _make_job(SessionLocal)

    response = test_client.post(f"/jobs/{job.id}/tailor/generate")
    assert response.status_code == 404
    assert "load_resume.py" in response.json()["detail"]


def test_generate_returns_draft_without_persisting(client_factory):
    test_client, SessionLocal = client_factory(FakeGeminiClient("Tailored draft text"))
    job = _make_job(SessionLocal)
    db = SessionLocal()
    crud.save_master_resume(db, "Master resume content")
    db.close()

    response = test_client.post(f"/jobs/{job.id}/tailor/generate")
    assert response.status_code == 200
    assert response.json()["draft"] == "Tailored draft text"

    get_response = test_client.get(f"/jobs/{job.id}")
    assert get_response.json()["status"] == "new"
    assert get_response.json()["tailored_resume_text"] is None


def test_generate_returns_502_on_gemini_error(client_factory):
    test_client, SessionLocal = client_factory(FakeGeminiClient(GeminiError("boom")))
    job = _make_job(SessionLocal)
    db = SessionLocal()
    crud.save_master_resume(db, "Master resume content")
    db.close()

    response = test_client.post(f"/jobs/{job.id}/tailor/generate")
    assert response.status_code == 502


def test_save_persists_and_transitions_status(client_factory):
    test_client, SessionLocal = client_factory(FakeGeminiClient("unused"))
    job = _make_job(SessionLocal)

    response = test_client.post(
        f"/jobs/{job.id}/tailor", json={"resume_text": "Edited tailored text"}
    )
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "tailored"
    assert body["tailored_resume_text"] == "Edited tailored text"


def test_save_returns_409_for_applied_job(client_factory):
    test_client, SessionLocal = client_factory(FakeGeminiClient("unused"))
    job = _make_job(SessionLocal)
    db = SessionLocal()
    job_in_session = crud.get_job(db, job.id)
    crud.update_job_status(db, job_in_session, JobStatus.tailored)
    crud.mark_applied(db, job_in_session, applied_date=date(2026, 8, 20))
    db.close()

    response = test_client.post(
        f"/jobs/{job.id}/tailor", json={"resume_text": "New text"}
    )
    assert response.status_code == 409
