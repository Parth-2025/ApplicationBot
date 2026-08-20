# Job Intake & Tracking Core Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the SQLite-backed data model, FastAPI JSON API, and React+antd dashboard that tracks internship postings and applications, forming the foundation later sub-projects (discovery, tailoring, notifications) plug into.

**Architecture:** A FastAPI backend (SQLAlchemy models over SQLite) exposes a small REST API for listing jobs, viewing job detail, updating status, and marking applications as submitted. A React + antd frontend consumes that API to render a job list table, a job detail view with an embedded resume viewer, and a mark-applied workflow. Both run locally on `localhost` only.

**Tech Stack:** Python 3.11+, FastAPI, SQLAlchemy, SQLite, pytest, httpx; Node.js, Vite, React, TypeScript, antd, react-router-dom, dayjs.

**Spec:** docs/superpowers/specs/2026-08-19-job-intake-tracking-core-design.md

## Global Constraints

- Single-user local tool: backend binds to `localhost` only, no auth.
- No automated application submission — status can only reach `applied` via the user-triggered mark-applied action, which requires an `applied_date`.
- `jobs` table enforces uniqueness on `(company, role_title, source_url)`; a repeat insert updates the existing row instead of creating a duplicate.
- `eligibility` is a fixed enum: `soph_junior`, `all_levels`, `freshman_only`, `senior_only`, `other`.
- `status` is a fixed enum: `new`, `tailored`, `applied`, `rejected`, `ignored`, with allowed transitions: `new` → {`tailored`, `ignored`, `rejected`}, `tailored` → {`applied`, `ignored`, `rejected`}, `applied` → {`rejected`}, `rejected`/`ignored` → {} (terminal).
- Backend testing: pytest with an in-memory SQLite database (no real DB file touched in tests).
- Frontend testing: manual verification only, per spec — no automated frontend test suite in this plan.

---

### Task 1: Backend scaffolding & SQLAlchemy models

**Files:**
- Create: `backend/requirements.txt`
- Create: `backend/app/__init__.py`
- Create: `backend/app/database.py`
- Create: `backend/app/models.py`
- Create: `backend/tests/__init__.py`
- Create: `backend/tests/conftest.py`
- Test: `backend/tests/test_models.py`

**Interfaces:**
- Produces: `app.database.Base` (SQLAlchemy declarative base), `app.database.SessionLocal`, `app.database.get_db()` generator, `app.database.engine`
- Produces: `app.models.Eligibility` (str enum: `soph_junior`, `all_levels`, `freshman_only`, `senior_only`, `other`), `app.models.JobStatus` (str enum: `new`, `tailored`, `applied`, `rejected`, `ignored`), `app.models.Job`, `app.models.Application` (SQLAlchemy models per spec's data model, with `Job.applications` relationship back-populated by `Application.job`)

- [ ] **Step 1: Create root .gitignore**

```text
backend/venv/
backend/__pycache__/
backend/**/__pycache__/
backend/*.db
backend/.pytest_cache/

# frontend
frontend/node_modules/
frontend/dist/
```

Write this to `.gitignore` at the repo root.

- [ ] **Step 2: Create requirements.txt and install dependencies**

```text
fastapi
uvicorn[standard]
sqlalchemy
pydantic
pytest
httpx
```

Run: `cd backend && python3 -m venv venv && source venv/bin/activate && pip install -r requirements.txt`

- [ ] **Step 3: Create package init files**

`backend/app/__init__.py` — empty file.
`backend/tests/__init__.py` — empty file.

- [ ] **Step 4: Write database.py**

```python
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

SQLALCHEMY_DATABASE_URL = "sqlite:///./applicationbot.db"

engine = create_engine(
    SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False}
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
```

- [ ] **Step 5: Write the failing test for models**

```python
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
```

```python
# backend/tests/conftest.py
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.database import Base


@pytest.fixture()
def db_session():
    engine = create_engine(
        "sqlite:///:memory:", connect_args={"check_same_thread": False}
    )
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()
```

- [ ] **Step 6: Run test to verify it fails**

Run: `cd backend && pytest tests/test_models.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.models'` (models.py doesn't exist yet)

- [ ] **Step 7: Write models.py**

```python
import enum
from sqlalchemy import (
    Column, Integer, String, Boolean, Date, Text, Enum, ForeignKey, UniqueConstraint
)
from sqlalchemy.orm import relationship
from .database import Base


class Eligibility(str, enum.Enum):
    soph_junior = "soph_junior"
    all_levels = "all_levels"
    freshman_only = "freshman_only"
    senior_only = "senior_only"
    other = "other"


class JobStatus(str, enum.Enum):
    new = "new"
    tailored = "tailored"
    applied = "applied"
    rejected = "rejected"
    ignored = "ignored"


class Job(Base):
    __tablename__ = "jobs"
    __table_args__ = (
        UniqueConstraint("company", "role_title", "source_url", name="uq_job_identity"),
    )

    id = Column(Integer, primary_key=True)
    company = Column(String, nullable=False)
    role_title = Column(String, nullable=False)
    source = Column(String, nullable=False)
    source_url = Column(String, nullable=False)
    location = Column(String, nullable=True)
    paid = Column(Boolean, nullable=False, default=True)
    eligibility = Column(Enum(Eligibility), nullable=False, default=Eligibility.other)
    posted_date = Column(Date, nullable=True)
    discovered_date = Column(Date, nullable=False)
    status = Column(Enum(JobStatus), nullable=False, default=JobStatus.new)
    raw_job_description = Column(Text, nullable=True)

    applications = relationship(
        "Application", back_populates="job", cascade="all, delete-orphan"
    )


class Application(Base):
    __tablename__ = "applications"

    id = Column(Integer, primary_key=True)
    job_id = Column(Integer, ForeignKey("jobs.id"), nullable=False)
    tailored_resume_path = Column(String, nullable=True)
    contact_email = Column(String, nullable=True)
    applied_date = Column(Date, nullable=True)
    application_number = Column(String, nullable=True)
    notes = Column(Text, nullable=True)

    job = relationship("Job", back_populates="applications")
```

- [ ] **Step 8: Run test to verify it passes**

Run: `cd backend && pytest tests/test_models.py -v`
Expected: PASS (2 tests)

- [ ] **Step 9: Commit**

```bash
git add .gitignore backend/requirements.txt backend/app/__init__.py backend/app/database.py backend/app/models.py backend/tests/__init__.py backend/tests/conftest.py backend/tests/test_models.py
git commit -m "feat: add SQLAlchemy models for jobs and applications"
```

---

### Task 2: Pydantic schemas & CRUD layer with status-transition validation

**Files:**
- Create: `backend/app/schemas.py`
- Create: `backend/app/crud.py`
- Test: `backend/tests/test_crud.py`

**Interfaces:**
- Consumes: `app.database.Base`, `app.models.Job`, `app.models.Application`, `app.models.Eligibility`, `app.models.JobStatus` (from Task 1)
- Produces: `app.schemas.JobCreate`, `app.schemas.JobUpdate`, `app.schemas.JobOut` (Pydantic models)
- Produces: `app.crud.InvalidStatusTransition` (Exception), `app.crud.create_or_update_job(db, job_in: schemas.JobCreate) -> models.Job`, `app.crud.get_job(db, job_id: int) -> models.Job | None`, `app.crud.list_jobs(db) -> list[models.Job]`, `app.crud.update_job_status(db, job: models.Job, new_status: models.JobStatus) -> models.Job`, `app.crud.mark_applied(db, job: models.Job, applied_date: date, application_number: str | None = None, notes: str | None = None) -> models.Job`

- [ ] **Step 1: Write schemas.py**

```python
from datetime import date
from typing import Optional
from pydantic import BaseModel, ConfigDict
from .models import Eligibility, JobStatus


class JobBase(BaseModel):
    company: str
    role_title: str
    source: str
    source_url: str
    location: Optional[str] = None
    paid: bool = True
    eligibility: Eligibility = Eligibility.other
    posted_date: Optional[date] = None
    raw_job_description: Optional[str] = None


class JobCreate(JobBase):
    discovered_date: date


class JobUpdate(BaseModel):
    status: Optional[JobStatus] = None
    applied_date: Optional[date] = None
    application_number: Optional[str] = None
    notes: Optional[str] = None


class JobOut(JobBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    discovered_date: date
    status: JobStatus
```

- [ ] **Step 2: Write the failing test for crud**

```python
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
```

- [ ] **Step 3: Run test to verify it fails**

Run: `cd backend && pytest tests/test_crud.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.crud'`

- [ ] **Step 4: Write crud.py**

```python
from datetime import date
from sqlalchemy.orm import Session
from . import models, schemas


class InvalidStatusTransition(Exception):
    pass


ALLOWED_TRANSITIONS = {
    models.JobStatus.new: {models.JobStatus.tailored, models.JobStatus.ignored, models.JobStatus.rejected},
    models.JobStatus.tailored: {models.JobStatus.applied, models.JobStatus.ignored, models.JobStatus.rejected},
    models.JobStatus.applied: {models.JobStatus.rejected},
    models.JobStatus.rejected: set(),
    models.JobStatus.ignored: set(),
}


def create_or_update_job(db: Session, job_in: schemas.JobCreate) -> models.Job:
    existing = (
        db.query(models.Job)
        .filter_by(
            company=job_in.company,
            role_title=job_in.role_title,
            source_url=job_in.source_url,
        )
        .first()
    )
    if existing:
        existing.discovered_date = job_in.discovered_date
        existing.raw_job_description = job_in.raw_job_description
        existing.paid = job_in.paid
        existing.eligibility = job_in.eligibility
        existing.location = job_in.location
        existing.posted_date = job_in.posted_date
        db.commit()
        db.refresh(existing)
        return existing

    job = models.Job(**job_in.model_dump())
    db.add(job)
    db.commit()
    db.refresh(job)
    return job


def get_job(db: Session, job_id: int) -> models.Job | None:
    return db.query(models.Job).filter(models.Job.id == job_id).first()


def list_jobs(db: Session) -> list[models.Job]:
    return db.query(models.Job).order_by(models.Job.discovered_date.desc()).all()


def update_job_status(
    db: Session, job: models.Job, new_status: models.JobStatus
) -> models.Job:
    if new_status not in ALLOWED_TRANSITIONS[job.status]:
        raise InvalidStatusTransition(
            f"Cannot transition job {job.id} from {job.status} to {new_status}"
        )
    job.status = new_status
    db.commit()
    db.refresh(job)
    return job


def mark_applied(
    db: Session,
    job: models.Job,
    applied_date: date,
    application_number: str | None = None,
    notes: str | None = None,
) -> models.Job:
    job = update_job_status(db, job, models.JobStatus.applied)
    application = models.Application(
        job_id=job.id,
        applied_date=applied_date,
        application_number=application_number,
        notes=notes,
    )
    db.add(application)
    db.commit()
    db.refresh(job)
    return job
```

- [ ] **Step 5: Run test to verify it passes**

Run: `cd backend && pytest tests/test_crud.py -v`
Expected: PASS (5 tests)

- [ ] **Step 6: Commit**

```bash
git add backend/app/schemas.py backend/app/crud.py backend/tests/test_crud.py
git commit -m "feat: add job schemas and crud layer with status-transition validation"
```

---

### Task 3: FastAPI routers and app wiring

**Files:**
- Create: `backend/app/routers/__init__.py`
- Create: `backend/app/routers/jobs.py`
- Create: `backend/app/main.py`
- Test: `backend/tests/test_jobs_api.py`

**Interfaces:**
- Consumes: `app.crud.*`, `app.schemas.*`, `app.models.JobStatus`, `app.database.get_db`, `app.database.Base`, `app.database.engine` (from Tasks 1-2)
- Produces: `app.main.app` (FastAPI instance) with router mounted at `/jobs` — `GET /jobs`, `GET /jobs/{job_id}`, `PATCH /jobs/{job_id}`, `GET /jobs/{job_id}/resume`

- [ ] **Step 1: Create routers package init**

`backend/app/routers/__init__.py` — empty file.

- [ ] **Step 2: Write the failing API test**

```python
# backend/tests/test_jobs_api.py
from datetime import date
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.main import app
from app.database import Base, get_db
from app import crud, schemas


@pytest.fixture()
def client():
    engine = create_engine(
        "sqlite:///:memory:", connect_args={"check_same_thread": False}
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
    crud.update_job_status(db, job, __import__("app.models", fromlist=["JobStatus"]).JobStatus.tailored)
    db.close()

    response = test_client.patch(f"/jobs/{job.id}", json={"status": "applied"})
    assert response.status_code == 422
```

- [ ] **Step 3: Run test to verify it fails**

Run: `cd backend && pytest tests/test_jobs_api.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.main'`

- [ ] **Step 4: Write routers/jobs.py**

```python
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from .. import crud, models, schemas
from ..database import get_db

router = APIRouter(prefix="/jobs", tags=["jobs"])


@router.get("", response_model=list[schemas.JobOut])
def list_jobs(db: Session = Depends(get_db)):
    return crud.list_jobs(db)


@router.get("/{job_id}", response_model=schemas.JobOut)
def get_job(job_id: int, db: Session = Depends(get_db)):
    job = crud.get_job(db, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


@router.patch("/{job_id}", response_model=schemas.JobOut)
def update_job(
    job_id: int, job_update: schemas.JobUpdate, db: Session = Depends(get_db)
):
    job = crud.get_job(db, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")

    if job_update.status is None:
        raise HTTPException(status_code=422, detail="No valid update fields provided")

    if job_update.status == models.JobStatus.applied:
        if job_update.applied_date is None:
            raise HTTPException(
                status_code=422,
                detail="applied_date is required when marking a job applied",
            )
        try:
            return crud.mark_applied(
                db,
                job,
                applied_date=job_update.applied_date,
                application_number=job_update.application_number,
                notes=job_update.notes,
            )
        except crud.InvalidStatusTransition as exc:
            raise HTTPException(status_code=409, detail=str(exc))

    try:
        return crud.update_job_status(db, job, job_update.status)
    except crud.InvalidStatusTransition as exc:
        raise HTTPException(status_code=409, detail=str(exc))


@router.get("/{job_id}/resume")
def get_resume(job_id: int, db: Session = Depends(get_db)):
    job = crud.get_job(db, job_id)
    if job is None or not job.applications:
        raise HTTPException(status_code=404, detail="No tailored resume for this job")
    resume_path = job.applications[-1].tailored_resume_path
    if not resume_path:
        raise HTTPException(status_code=404, detail="No tailored resume for this job")
    return FileResponse(resume_path, media_type="application/pdf")
```

- [ ] **Step 5: Write main.py**

```python
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from .database import Base, engine
from .routers import jobs

Base.metadata.create_all(bind=engine)

app = FastAPI(title="ApplicationBot API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(jobs.router)
```

- [ ] **Step 6: Run test to verify it passes**

Run: `cd backend && pytest tests/test_jobs_api.py -v`
Expected: PASS (6 tests)

- [ ] **Step 7: Run the full backend test suite**

Run: `cd backend && pytest -v`
Expected: PASS (13 tests total across test_models.py, test_crud.py, test_jobs_api.py)

- [ ] **Step 8: Commit**

```bash
git add backend/app/routers/__init__.py backend/app/routers/jobs.py backend/app/main.py backend/tests/test_jobs_api.py
git commit -m "feat: add FastAPI routers for job listing, detail, status update, and resume download"
```

---

### Task 4: Frontend scaffolding and API client

**Files:**
- Create: `frontend/` (via Vite scaffold — package.json, tsconfig.json, vite.config.ts, index.html, src/main.tsx, src/App.tsx generated by the tool, then modified below)
- Create: `frontend/src/api/client.ts`
- Modify: `frontend/src/main.tsx`
- Modify: `frontend/src/App.tsx`

**Interfaces:**
- Consumes: backend API from Task 3 (`GET /jobs`, `GET /jobs/{id}`, `PATCH /jobs/{id}`, `GET /jobs/{id}/resume`), running at `http://localhost:8000`
- Produces: `Job` type, `fetchJobs()`, `fetchJob(id)`, `updateJobStatus(id, status)`, `markApplied(id, payload)`, `MarkAppliedPayload` type — exported from `src/api/client.ts` for use by Tasks 5-6

- [ ] **Step 1: Scaffold the Vite React TypeScript project**

Run: `cd /Users/parthmohan/Desktop/ApplicationBot && npm create vite@latest frontend -- --template react-ts`

- [ ] **Step 2: Install dependencies**

Run: `cd frontend && npm install && npm install antd react-router-dom dayjs`

- [ ] **Step 3: Write the API client**

```typescript
// frontend/src/api/client.ts
export interface Job {
  id: number;
  company: string;
  role_title: string;
  source: string;
  source_url: string;
  location: string | null;
  paid: boolean;
  eligibility: string;
  posted_date: string | null;
  discovered_date: string;
  status: "new" | "tailored" | "applied" | "rejected" | "ignored";
  raw_job_description: string | null;
}

const API_BASE = "http://localhost:8000";

export async function fetchJobs(): Promise<Job[]> {
  const res = await fetch(`${API_BASE}/jobs`);
  if (!res.ok) throw new Error("Failed to fetch jobs");
  return res.json();
}

export async function fetchJob(id: number): Promise<Job> {
  const res = await fetch(`${API_BASE}/jobs/${id}`);
  if (!res.ok) throw new Error("Failed to fetch job");
  return res.json();
}

export interface MarkAppliedPayload {
  status: "applied";
  applied_date: string;
  application_number?: string;
  notes?: string;
}

export async function markApplied(
  id: number,
  payload: MarkAppliedPayload
): Promise<Job> {
  const res = await fetch(`${API_BASE}/jobs/${id}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!res.ok) throw new Error("Failed to mark job applied");
  return res.json();
}

export async function updateJobStatus(id: number, status: string): Promise<Job> {
  const res = await fetch(`${API_BASE}/jobs/${id}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ status }),
  });
  if (!res.ok) throw new Error("Failed to update job status");
  return res.json();
}
```

- [ ] **Step 4: Replace main.tsx to import antd reset styles**

```tsx
// frontend/src/main.tsx
import React from "react";
import ReactDOM from "react-dom/client";
import "antd/dist/reset.css";
import App from "./App";

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>
);
```

- [ ] **Step 5: Replace App.tsx with a minimal router shell**

```tsx
// frontend/src/App.tsx
import { BrowserRouter, Routes, Route } from "react-router-dom";
import { ConfigProvider } from "antd";

export default function App() {
  return (
    <ConfigProvider>
      <BrowserRouter>
        <div style={{ padding: 24 }}>
          <Routes>
            <Route path="/" element={<div>Job list coming in Task 5</div>} />
          </Routes>
        </div>
      </BrowserRouter>
    </ConfigProvider>
  );
}
```

- [ ] **Step 6: Verify the dev server runs**

Run: `cd frontend && npm run dev`
Expected: Vite dev server starts on `http://localhost:5173`; open it in a browser and confirm the placeholder text "Job list coming in Task 5" renders with no console errors. Stop the server with Ctrl+C when confirmed.

- [ ] **Step 7: Commit**

`.gitignore` (added in Task 1) already excludes `frontend/node_modules/` and `frontend/dist/`, so it's safe to add the whole `frontend` directory.

```bash
cd /Users/parthmohan/Desktop/ApplicationBot
git add frontend
git commit -m "feat: scaffold React+TS+antd frontend with API client"
```

---

### Task 5: Job list table page

**Files:**
- Create: `frontend/src/components/JobTable.tsx`
- Modify: `frontend/src/App.tsx`

**Interfaces:**
- Consumes: `Job`, `fetchJobs()` from `frontend/src/api/client.ts` (Task 4)
- Produces: `JobTable` component (default export), rendered at route `/`

- [ ] **Step 1: Write JobTable.tsx**

```tsx
// frontend/src/components/JobTable.tsx
import { useEffect, useState } from "react";
import { Table, Tag, message } from "antd";
import type { ColumnsType } from "antd/es/table";
import { Link } from "react-router-dom";
import { fetchJobs, Job } from "../api/client";

const statusColors: Record<Job["status"], string> = {
  new: "blue",
  tailored: "gold",
  applied: "green",
  rejected: "red",
  ignored: "default",
};

export default function JobTable() {
  const [jobs, setJobs] = useState<Job[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetchJobs()
      .then(setJobs)
      .catch(() => message.error("Failed to load jobs"))
      .finally(() => setLoading(false));
  }, []);

  const columns: ColumnsType<Job> = [
    {
      title: "Company",
      dataIndex: "company",
      sorter: (a, b) => a.company.localeCompare(b.company),
    },
    { title: "Role", dataIndex: "role_title" },
    {
      title: "Status",
      dataIndex: "status",
      filters: Object.keys(statusColors).map((s) => ({ text: s, value: s })),
      onFilter: (value, record) => record.status === value,
      render: (status: Job["status"]) => (
        <Tag color={statusColors[status]}>{status}</Tag>
      ),
    },
    { title: "Eligibility", dataIndex: "eligibility" },
    {
      title: "Discovered",
      dataIndex: "discovered_date",
      sorter: (a, b) => a.discovered_date.localeCompare(b.discovered_date),
    },
    {
      title: "",
      key: "actions",
      render: (_, record) => <Link to={`/jobs/${record.id}`}>View</Link>,
    },
  ];

  return <Table rowKey="id" loading={loading} columns={columns} dataSource={jobs} />;
}
```

- [ ] **Step 2: Wire JobTable into App.tsx's root route**

```tsx
// frontend/src/App.tsx
import { BrowserRouter, Routes, Route } from "react-router-dom";
import { ConfigProvider } from "antd";
import JobTable from "./components/JobTable";

export default function App() {
  return (
    <ConfigProvider>
      <BrowserRouter>
        <div style={{ padding: 24 }}>
          <Routes>
            <Route path="/" element={<JobTable />} />
          </Routes>
        </div>
      </BrowserRouter>
    </ConfigProvider>
  );
}
```

- [ ] **Step 3: Manually verify against the running backend**

Run: `cd backend && source venv/bin/activate && uvicorn app.main:app --reload` (leave running)
Run in a second terminal: `cd frontend && npm run dev`
Expected: Open `http://localhost:5173` — table renders (empty, since no jobs are seeded yet); no console errors. Confirm via the Network tab that a `GET http://localhost:8000/jobs` request succeeds with a 200 and CORS is not blocked.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components/JobTable.tsx frontend/src/App.tsx
git commit -m "feat: add job list table page"
```

---

### Task 6: Job detail page and mark-applied workflow

**Files:**
- Create: `frontend/src/components/JobDetail.tsx`
- Create: `frontend/src/components/MarkAppliedModal.tsx`
- Modify: `frontend/src/App.tsx`

**Interfaces:**
- Consumes: `Job`, `fetchJob(id)`, `updateJobStatus(id, status)`, `markApplied(id, payload)`, `MarkAppliedPayload` from `frontend/src/api/client.ts` (Task 4)
- Produces: `JobDetail` component (default export) at route `/jobs/:id`; `MarkAppliedModal` component (default export), consumed by `JobDetail`

- [ ] **Step 1: Write MarkAppliedModal.tsx**

```tsx
// frontend/src/components/MarkAppliedModal.tsx
import { Modal, Form, DatePicker, Input, message } from "antd";
import dayjs from "dayjs";
import { markApplied } from "../api/client";

interface Props {
  jobId: number;
  open: boolean;
  onClose: () => void;
  onSuccess: () => void;
}

export default function MarkAppliedModal({ jobId, open, onClose, onSuccess }: Props) {
  const [form] = Form.useForm();

  const handleOk = async () => {
    try {
      const values = await form.validateFields();
      await markApplied(jobId, {
        status: "applied",
        applied_date: values.applied_date.format("YYYY-MM-DD"),
        application_number: values.application_number,
        notes: values.notes,
      });
      message.success("Marked as applied");
      form.resetFields();
      onSuccess();
    } catch (err) {
      if (err instanceof Error) message.error(err.message);
    }
  };

  return (
    <Modal title="Mark Applied" open={open} onOk={handleOk} onCancel={onClose}>
      <Form form={form} layout="vertical" initialValues={{ applied_date: dayjs() }}>
        <Form.Item name="applied_date" label="Applied Date" rules={[{ required: true }]}>
          <DatePicker style={{ width: "100%" }} />
        </Form.Item>
        <Form.Item name="application_number" label="Application Number">
          <Input />
        </Form.Item>
        <Form.Item name="notes" label="Notes">
          <Input.TextArea rows={3} />
        </Form.Item>
      </Form>
    </Modal>
  );
}
```

- [ ] **Step 2: Write JobDetail.tsx**

```tsx
// frontend/src/components/JobDetail.tsx
import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import { Descriptions, Button, Space, message } from "antd";
import { fetchJob, updateJobStatus, Job } from "../api/client";
import MarkAppliedModal from "./MarkAppliedModal";

export default function JobDetail() {
  const { id } = useParams();
  const [job, setJob] = useState<Job | null>(null);
  const [modalOpen, setModalOpen] = useState(false);

  const load = () => {
    if (!id) return;
    fetchJob(Number(id))
      .then(setJob)
      .catch(() => message.error("Failed to load job"));
  };

  useEffect(load, [id]);

  if (!job) return null;

  const handleIgnore = async () => {
    try {
      await updateJobStatus(job.id, "ignored");
      message.success("Job marked ignored");
      load();
    } catch {
      message.error("Failed to update job");
    }
  };

  return (
    <div>
      <Descriptions title={`${job.company} — ${job.role_title}`} bordered column={1}>
        <Descriptions.Item label="Status">{job.status}</Descriptions.Item>
        <Descriptions.Item label="Eligibility">{job.eligibility}</Descriptions.Item>
        <Descriptions.Item label="Location">{job.location ?? "—"}</Descriptions.Item>
        <Descriptions.Item label="Source">
          <a href={job.source_url} target="_blank" rel="noreferrer">
            {job.source}
          </a>
        </Descriptions.Item>
        <Descriptions.Item label="Job Description">
          {job.raw_job_description ?? "—"}
        </Descriptions.Item>
      </Descriptions>

      {job.status === "tailored" && (
        <div style={{ margin: "16px 0" }}>
          <iframe
            title="tailored-resume"
            src={`http://localhost:8000/jobs/${job.id}/resume`}
            width="100%"
            height="600px"
          />
        </div>
      )}

      <Space style={{ marginTop: 16 }}>
        {job.status === "tailored" && (
          <Button type="primary" onClick={() => setModalOpen(true)}>
            Mark Applied
          </Button>
        )}
        {(job.status === "new" || job.status === "tailored") && (
          <Button danger onClick={handleIgnore}>
            Ignore
          </Button>
        )}
      </Space>

      <MarkAppliedModal
        jobId={job.id}
        open={modalOpen}
        onClose={() => setModalOpen(false)}
        onSuccess={() => {
          setModalOpen(false);
          load();
        }}
      />
    </div>
  );
}
```

- [ ] **Step 3: Wire the detail route into App.tsx**

```tsx
// frontend/src/App.tsx
import { BrowserRouter, Routes, Route } from "react-router-dom";
import { ConfigProvider } from "antd";
import JobTable from "./components/JobTable";
import JobDetail from "./components/JobDetail";

export default function App() {
  return (
    <ConfigProvider>
      <BrowserRouter>
        <div style={{ padding: 24 }}>
          <Routes>
            <Route path="/" element={<JobTable />} />
            <Route path="/jobs/:id" element={<JobDetail />} />
          </Routes>
        </div>
      </BrowserRouter>
    </ConfigProvider>
  );
}
```

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components/JobDetail.tsx frontend/src/components/MarkAppliedModal.tsx frontend/src/App.tsx
git commit -m "feat: add job detail page and mark-applied workflow"
```

---

### Task 7: Seed script and end-to-end manual verification

**Files:**
- Create: `backend/seed.py`

**Interfaces:**
- Consumes: `app.database.SessionLocal`, `app.database.Base`, `app.database.engine`, `app.crud.create_or_update_job`, `app.crud.update_job_status`, `app.schemas.JobCreate`, `app.models.JobStatus`, `app.models.Eligibility` (from Tasks 1-3)

- [ ] **Step 1: Write seed.py**

```python
# backend/seed.py
from datetime import date
from app.database import SessionLocal, Base, engine
from app import crud, schemas
from app.models import JobStatus, Eligibility

Base.metadata.create_all(bind=engine)

db = SessionLocal()

job1 = crud.create_or_update_job(
    db,
    schemas.JobCreate(
        company="Example Corp",
        role_title="AI Engineering Intern",
        source="manual-seed",
        source_url="https://example.com/jobs/1",
        location="Remote",
        paid=True,
        eligibility=Eligibility.soph_junior,
        discovered_date=date.today(),
        raw_job_description="Build and evaluate LLM-powered features.",
    ),
)

job2 = crud.create_or_update_job(
    db,
    schemas.JobCreate(
        company="Sample Inc",
        role_title="SWE Intern",
        source="manual-seed",
        source_url="https://example.com/jobs/2",
        location="Maryland",
        paid=True,
        eligibility=Eligibility.soph_junior,
        discovered_date=date.today(),
        raw_job_description="Full-stack web development on core product.",
    ),
)
crud.update_job_status(db, job2, JobStatus.tailored)

db.close()
print("Seeded 2 sample jobs.")
```

- [ ] **Step 2: Run the seed script against a fresh local database**

Run: `cd backend && rm -f applicationbot.db && source venv/bin/activate && python seed.py`
Expected: prints `Seeded 2 sample jobs.`; `backend/applicationbot.db` is created.

- [ ] **Step 3: Run the full manual end-to-end check**

Run: `cd backend && source venv/bin/activate && uvicorn app.main:app --reload` (leave running)
Run in a second terminal: `cd frontend && npm run dev` (leave running)

Manually verify in a browser at `http://localhost:5173`:
1. Job list table shows "Example Corp — AI Engineering Intern" (status `new`) and "Sample Inc — SWE Intern" (status `tailored`).
2. Click "View" on the `new` job — detail page shows company, role, eligibility, location, source link, job description; no resume iframe (not tailored yet); "Ignore" button is present, "Mark Applied" is not.
3. Go back, click "View" on the `tailored` job — detail page shows a resume iframe (it will 404 inside the iframe since no PDF path is set yet, which is expected — no tailoring engine exists yet); both "Mark Applied" and "Ignore" buttons are present.
4. Click "Mark Applied", fill in today's date and an application number, submit — success message appears, page reloads to show status `applied`, "Mark Applied"/"Ignore" buttons disappear (per allowed transitions, `applied` can only go to `rejected`).
5. Go back to the job list — confirm the status tag updated to `applied` (green).

- [ ] **Step 4: Commit**

```bash
git add backend/seed.py
git commit -m "chore: add seed script for manual end-to-end verification"
```
