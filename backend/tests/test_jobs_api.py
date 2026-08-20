from datetime import date
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.main import app
from app.database import Base, get_db
from app import crud, schemas
from app.models import JobStatus


@pytest.fixture()
def client():
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
    yield TestClient(app), TestingSessionLocal
    app.dependency_overrides.clear()


def test_list_jobs_empty(client):
    test_client, _ = client
    response = test_client.get("/jobs")
    assert response.status_code == 200
    assert response.json() == []


def test_get_job_by_id(client):
    test_client, SessionLocal = client
    db = SessionLocal()
    job = crud.create_or_update_job(
        db,
        schemas.JobCreate(
            company="Acme",
            role_title="ML Intern",
            source="simplify",
            source_url="https://example.com/acme-ml",
            discovered_date=date(2026, 8, 19),
        ),
    )
    db.close()

    response = test_client.get(f"/jobs/{job.id}")
    assert response.status_code == 200
    assert response.json()["company"] == "Acme"


def test_get_job_not_found(client):
    test_client, _ = client
    response = test_client.get("/jobs/999")
    assert response.status_code == 404


def test_valid_status_transition_via_api(client):
    test_client, SessionLocal = client
    db = SessionLocal()
    job = crud.create_or_update_job(
        db,
        schemas.JobCreate(
            company="Acme",
            role_title="SWE Intern",
            source="simplify",
            source_url="https://example.com/acme-swe",
            discovered_date=date(2026, 8, 19),
        ),
    )
    db.close()

    response = test_client.patch(f"/jobs/{job.id}", json={"status": "tailored"})
    assert response.status_code == 200
    assert response.json()["status"] == "tailored"


def test_invalid_status_transition_returns_409(client):
    test_client, SessionLocal = client
    db = SessionLocal()
    job = crud.create_or_update_job(
        db,
        schemas.JobCreate(
            company="Acme",
            role_title="AI Intern",
            source="simplify",
            source_url="https://example.com/acme-ai",
            discovered_date=date(2026, 8, 19),
        ),
    )
    db.close()

    response = test_client.patch(
        f"/jobs/{job.id}",
        json={"status": "applied", "applied_date": "2026-08-20"},
    )
    assert response.status_code == 409


def test_mark_applied_without_date_returns_422(client):
    test_client, SessionLocal = client
    db = SessionLocal()
    job = crud.create_or_update_job(
        db,
        schemas.JobCreate(
            company="Acme",
            role_title="Data Intern",
            source="simplify",
            source_url="https://example.com/acme-data",
            discovered_date=date(2026, 8, 19),
        ),
    )
    crud.update_job_status(db, job, JobStatus.tailored)
    db.close()

    response = test_client.patch(f"/jobs/{job.id}", json={"status": "applied"})
    assert response.status_code == 422
