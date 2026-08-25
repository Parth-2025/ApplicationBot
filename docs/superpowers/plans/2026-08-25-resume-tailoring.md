# Resume Tailoring Assist Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let the user generate a Gemini-tailored version of their resume for a specific job posting, review/edit it in the browser, and save it — moving the job from `new` to `tailored`.

**Architecture:** A one-time CLI script extracts the user's master resume PDF to text and stores it in a new `MasterResume` table. A new `app/tailoring.py` module builds a Gemini prompt from that text plus a job's details (with hard structural constraints so the output is a same-length, same-format drop-in replacement, not a rewrite) and calls a new `GeminiClient.generate_text` method. Two new endpoints on the existing jobs router generate a draft (unsaved) and save a (possibly user-edited) draft, reusing the existing `Application`/status-transition machinery. The frontend job detail page gets a generate button, an editable textarea, and a save button.

**Tech Stack:** Python/FastAPI/SQLAlchemy (existing backend), `pypdf` (new dependency, PDF text extraction), the existing `discovery.gemini_client.GeminiClient`, React/antd (existing frontend), `pytest`.

**Spec:** docs/superpowers/specs/2026-08-25-resume-tailoring-design.md

**Prerequisite:** Sub-projects 1 (Job Intake & Tracking Core) and 2 (Job Discovery) are merged — `backend/app/{database,models,schemas,crud}.py`, `backend/app/routers/jobs.py`, `backend/discovery/gemini_client.py`, and the frontend job list/detail pages already exist and their tests pass before Task 1 begins.

## Global Constraints

- The tailored output must preserve the master resume's exact section structure, section order, and number of bullets per entry — only wording changes. This is enforced via explicit instructions in the Gemini prompt (`app/tailoring.py`), not via code-level validation; the editable-draft review step in the UI is the actual safety net.
- No PDF generation and no cover letters — tailoring produces plain text only, for the user to paste into their own resume template.
- No automated application submission — unaffected by this work.
- Reuse `discovery.gemini_client.GeminiClient` for the Gemini call — do not write a second Gemini-calling client.
- Backend testing: pytest, no live network/Gemini calls in the automated suite — fake Gemini clients, matching the pattern already used in `tests/discovery/test_classifier.py` and `tests/discovery/test_pipeline.py`.
- Frontend has no test framework configured (matches existing sub-projects) — frontend verification is `npm run build` (type-check) plus manual click-through in the dev server.

---

### Task 1: `GeminiClient.generate_text` (plain-text Gemini calls)

**Files:**
- Modify: `backend/discovery/gemini_client.py`
- Test: `backend/tests/discovery/test_gemini_client.py`

**Interfaces:**
- Produces: `GeminiClient.generate_text(prompt: str, retries: int = 1) -> str` — same rate-limiting/timeout/retry/quota-detection behavior as the existing `generate_json`, but returns the raw response text instead of parsing it as JSON.

The existing `generate_json` has all the retry/pacing/quota-detection logic inline. Tailoring needs a plain-text response (a resume isn't JSON), so this task extracts that shared logic into a private helper both methods use — avoids duplicating the retry loop.

- [ ] **Step 1: Write the failing tests**

Add to `backend/tests/discovery/test_gemini_client.py` (uses the existing `FakeModel`/`FakeResponse` classes already in that file):

```python
def test_generate_text_returns_raw_text():
    model = FakeModel(["Some tailored resume text here."])
    client = GeminiClient(model=model, min_seconds_between_calls=0)
    assert client.generate_text("prompt") == "Some tailored resume text here."


def test_generate_text_retries_then_succeeds():
    model = FakeModel([RuntimeError("boom"), "final text"])
    client = GeminiClient(model=model, min_seconds_between_calls=0)
    result = client.generate_text("prompt", retries=1)
    assert result == "final text"
    assert model.calls == 2


def test_generate_text_raises_quota_exhausted_without_retrying():
    quota_error = RuntimeError(
        "429 quota exceeded ... GenerateRequestsPerDayPerProjectPerModel-FreeTier ..."
    )
    model = FakeModel([quota_error])
    client = GeminiClient(model=model, min_seconds_between_calls=0)
    with pytest.raises(GeminiQuotaExhaustedError):
        client.generate_text("prompt", retries=3)
    assert model.calls == 1
```

- [ ] **Step 2: Run the new tests to verify they fail**

Run: `cd backend && venv/bin/pytest tests/discovery/test_gemini_client.py -v -k generate_text`
Expected: FAIL with `AttributeError: 'GeminiClient' object has no attribute 'generate_text'`

- [ ] **Step 3: Refactor `GeminiClient` to add `generate_text`, sharing retry logic with `generate_json`**

Replace the existing `generate_json` method in `backend/discovery/gemini_client.py` with:

```python
    def _generate_with_retry(self, prompt: str, retries: int) -> str:
        last_error: Exception | None = None
        for attempt in range(retries + 1):
            self._wait_for_rate_limit()
            try:
                response = self._call_model(prompt)
                return response.text.strip()
            except Exception as exc:  # noqa: BLE001 - any Gemini SDK/network failure
                last_error = exc
                # Daily-quota exhaustion won't clear up by retrying seconds
                # later like a per-minute rate limit would - stop immediately
                # rather than burn the retry budget on a guaranteed failure.
                if "PerDay" in str(exc):
                    raise GeminiQuotaExhaustedError(
                        f"Gemini daily quota exhausted: {exc}"
                    ) from exc
                if attempt < retries:
                    time.sleep(2**attempt)
        raise GeminiError(f"Gemini call failed after {retries + 1} attempt(s): {last_error}")

    def generate_text(self, prompt: str, retries: int = 1) -> str:
        return self._generate_with_retry(prompt, retries)

    def generate_json(self, prompt: str, retries: int = 1):
        text = self._generate_with_retry(prompt, retries)
        if text.startswith("```"):
            text = text.strip("`")
            if text.lower().startswith("json"):
                text = text[4:]
        try:
            return json.loads(text.strip())
        except json.JSONDecodeError as exc:
            raise GeminiError(f"Gemini call returned invalid JSON: {exc}") from exc
```

- [ ] **Step 4: Run all gemini_client tests to verify they pass**

Run: `cd backend && venv/bin/pytest tests/discovery/test_gemini_client.py -v`
Expected: all PASS (the pre-existing `generate_json` tests still pass unchanged, plus the 3 new `generate_text` tests)

- [ ] **Step 5: Run the full test suite to confirm nothing else broke**

Run: `cd backend && venv/bin/pytest -q`
Expected: all PASS

- [ ] **Step 6: Commit**

```bash
git add backend/discovery/gemini_client.py backend/tests/discovery/test_gemini_client.py
git commit -m "feat: add GeminiClient.generate_text for plain-text responses"
```

---

### Task 2: `MasterResume` model, `Application.tailored_resume_text` rename, crud functions

**Files:**
- Modify: `backend/app/models.py`
- Modify: `backend/app/schemas.py`
- Modify: `backend/app/crud.py`
- Modify: `backend/tests/test_crud.py` (existing test references the old field name)
- Test: `backend/tests/test_crud.py` (new tests appended)

**Interfaces:**
- Produces: `models.MasterResume` (columns: `id`, `content: str`, `updated_date: date`), `models.Application.tailored_resume_text: str | None` (renamed from `tailored_resume_path`), `crud.get_master_resume(db) -> models.MasterResume | None`, `crud.save_master_resume(db, content: str) -> models.MasterResume`.

- [ ] **Step 1: Update the existing test that references the old field name**

In `backend/tests/test_crud.py`, in `test_mark_applied_updates_existing_application_record`, replace:

```python
    existing_application = models.Application(
        job_id=job.id,
        tailored_resume_path="/tmp/resume.pdf",
    )
```

with:

```python
    existing_application = models.Application(
        job_id=job.id,
        tailored_resume_text="Existing tailored resume text",
    )
```

And replace:

```python
    assert application.tailored_resume_path == "/tmp/resume.pdf"
```

with:

```python
    assert application.tailored_resume_text == "Existing tailored resume text"
```

Also update the comment two lines above the `existing_application =` assignment from `(e.g. with a tailored_resume_path)` to `(e.g. with a tailored_resume_text)`.

- [ ] **Step 2: Write the new failing tests for `MasterResume` crud functions**

Append to `backend/tests/test_crud.py`:

```python
def test_get_master_resume_returns_none_when_not_loaded(db_session):
    assert crud.get_master_resume(db_session) is None


def test_save_master_resume_creates_row(db_session):
    resume = crud.save_master_resume(db_session, "My resume content")
    assert resume.content == "My resume content"
    assert resume.updated_date == date.today()
    assert crud.get_master_resume(db_session).content == "My resume content"


def test_save_master_resume_overwrites_existing_row(db_session):
    crud.save_master_resume(db_session, "First version")
    crud.save_master_resume(db_session, "Second version")

    from app.models import MasterResume

    assert db_session.query(MasterResume).count() == 1
    assert crud.get_master_resume(db_session).content == "Second version"
```

- [ ] **Step 3: Run the new tests to verify they fail**

Run: `cd backend && venv/bin/pytest tests/test_crud.py -v -k master_resume`
Expected: FAIL with `AttributeError: module 'app.crud' has no attribute 'get_master_resume'`

- [ ] **Step 4: Add the `MasterResume` model and rename the `Application` field**

In `backend/app/models.py`, change:

```python
    tailored_resume_path = Column(String, nullable=True)
```

to:

```python
    tailored_resume_text = Column(Text, nullable=True)
```

(`Text` is already imported at the top of `models.py`.)

Append a new model at the end of the file:

```python
class MasterResume(Base):
    __tablename__ = "master_resumes"

    id = Column(Integer, primary_key=True)
    content = Column(Text, nullable=False)
    updated_date = Column(Date, nullable=False)
```

- [ ] **Step 5: Update `schemas.py`**

In `backend/app/schemas.py`, in `JobOut`, change:

```python
    tailored_resume_path: Optional[str] = None
```

to:

```python
    tailored_resume_text: Optional[str] = None
```

- [ ] **Step 6: Add crud functions**

In `backend/app/crud.py`, add near the top (after the imports, before `create_or_update_job`):

```python
def get_master_resume(db: Session) -> models.MasterResume | None:
    return db.query(models.MasterResume).filter(models.MasterResume.id == 1).first()


def save_master_resume(db: Session, content: str) -> models.MasterResume:
    resume = db.query(models.MasterResume).filter(models.MasterResume.id == 1).first()
    if resume is None:
        resume = models.MasterResume(id=1, content=content, updated_date=date.today())
        db.add(resume)
    else:
        resume.content = content
        resume.updated_date = date.today()
    db.commit()
    db.refresh(resume)
    return resume
```

- [ ] **Step 7: Fix the two remaining references to the old field name in `app/routers/jobs.py`**

These will be replaced properly in Task 6, but update them now so the app doesn't crash on import between tasks. In `backend/app/routers/jobs.py`, change:

```python
        job_out.tailored_resume_path = latest.tailored_resume_path
```

to:

```python
        job_out.tailored_resume_text = latest.tailored_resume_text
```

Also fix the `/resume` endpoint further down, which reads the same renamed attribute — change:

```python
    resume_path = job.applications[-1].tailored_resume_path
```

to:

```python
    resume_path = job.applications[-1].tailored_resume_text
```

This keeps the endpoint from throwing `AttributeError` in the gap before Task 6 removes it entirely — it's dead code at this point (nothing writes the field yet), so functional correctness doesn't matter here, just that the module imports and runs.

- [ ] **Step 8: Run the full test suite to verify everything passes**

Run: `cd backend && venv/bin/pytest -q`
Expected: all PASS

- [ ] **Step 9: Commit**

```bash
git add backend/app/models.py backend/app/schemas.py backend/app/crud.py backend/app/routers/jobs.py backend/tests/test_crud.py
git commit -m "feat: add MasterResume model and rename tailored_resume_path to tailored_resume_text"
```

---

### Task 3: `load_resume.py` CLI script

**Files:**
- Create: `backend/load_resume.py`
- Modify: `backend/requirements.txt`
- Test: `backend/tests/test_load_resume.py`

**Interfaces:**
- Consumes: `crud.save_master_resume(db, content) -> models.MasterResume` (Task 2)
- Produces: `load_resume.extract_text_from_pdf(pdf_path: Path) -> str`, `load_resume.main(pdf_path: str, db_session_factory=SessionLocal) -> None`

- [ ] **Step 1: Add `pypdf` to requirements**

In `backend/requirements.txt`, add a new line: `pypdf`

Run: `cd backend && venv/bin/pip install -r requirements.txt`

- [ ] **Step 2: Write the failing tests**

Create `backend/tests/test_load_resume.py`:

```python
# backend/tests/test_load_resume.py
from datetime import date

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app import crud
from app.models import MasterResume
import load_resume


@pytest.fixture()
def db_session_factory():
    engine = create_engine(
        "sqlite:///:memory:", connect_args={"check_same_thread": False}
    )
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)
    return TestingSessionLocal


def test_main_extracts_and_saves_master_resume(db_session_factory, monkeypatch):
    monkeypatch.setattr(
        load_resume, "extract_text_from_pdf", lambda path: "Fake resume text"
    )

    load_resume.main("/fake/path.pdf", db_session_factory=db_session_factory)

    db = db_session_factory()
    resume = crud.get_master_resume(db)
    assert resume is not None
    assert resume.content == "Fake resume text"
    assert resume.updated_date == date.today()


def test_main_overwrites_rather_than_duplicates(db_session_factory, monkeypatch):
    monkeypatch.setattr(
        load_resume, "extract_text_from_pdf", lambda path: "First version"
    )
    load_resume.main("/fake/path.pdf", db_session_factory=db_session_factory)

    monkeypatch.setattr(
        load_resume, "extract_text_from_pdf", lambda path: "Second version"
    )
    load_resume.main("/fake/path.pdf", db_session_factory=db_session_factory)

    db = db_session_factory()
    assert db.query(MasterResume).count() == 1
    assert crud.get_master_resume(db).content == "Second version"
```

- [ ] **Step 3: Run the tests to verify they fail**

Run: `cd backend && venv/bin/pytest tests/test_load_resume.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'load_resume'`

- [ ] **Step 4: Write `load_resume.py`**

Create `backend/load_resume.py`:

```python
# backend/load_resume.py
import sys
from pathlib import Path

import pypdf

from app import crud
from app.database import Base, SessionLocal, engine


def extract_text_from_pdf(pdf_path: Path) -> str:
    reader = pypdf.PdfReader(str(pdf_path))
    return "\n".join(page.extract_text() or "" for page in reader.pages)


def main(pdf_path: str, db_session_factory=SessionLocal) -> None:
    content = extract_text_from_pdf(Path(pdf_path))
    db = db_session_factory()
    try:
        crud.save_master_resume(db, content)
    finally:
        db.close()
    print(f"Loaded master resume from {pdf_path} ({len(content)} characters).")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: venv/bin/python load_resume.py <path-to-resume.pdf>")
        sys.exit(1)
    Base.metadata.create_all(bind=engine)
    main(sys.argv[1])
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `cd backend && venv/bin/pytest tests/test_load_resume.py -v`
Expected: both PASS

- [ ] **Step 6: Run the full test suite**

Run: `cd backend && venv/bin/pytest -q`
Expected: all PASS

- [ ] **Step 7: Commit**

```bash
git add backend/load_resume.py backend/requirements.txt backend/tests/test_load_resume.py
git commit -m "feat: add load_resume.py CLI to ingest the master resume PDF"
```

---

### Task 4: `app/tailoring.py` — tailored resume generation

**Files:**
- Create: `backend/app/tailoring.py`
- Test: `backend/tests/test_tailoring.py`

**Interfaces:**
- Consumes: `GeminiClient.generate_text(prompt, retries=1) -> str` (Task 1), `models.Job` (existing)
- Produces: `tailoring.generate_tailored_resume(client, master_resume_text: str, job: models.Job) -> str`

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_tailoring.py`:

```python
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
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd backend && venv/bin/pytest tests/test_tailoring.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.tailoring'`

- [ ] **Step 3: Write `app/tailoring.py`**

Create `backend/app/tailoring.py`:

```python
# backend/app/tailoring.py
from discovery.gemini_client import GeminiClient

from . import models

TAILOR_PROMPT_TEMPLATE = """You are helping a student tailor their resume for one specific internship posting.

Master resume (this is the student's real, current resume - a single page):
---
{master_resume}
---

Target posting:
Company: {company}
Role title: {role_title}
Description: {job_description}

Rewrite the master resume above so its wording is tailored to this posting - matching its language, emphasizing the most relevant experience, and aligning keywords where genuinely applicable.

Hard constraints, all of which must hold:
- Keep the exact same sections, in the exact same order, as the master resume.
- Keep the exact same number of bullet points under each role/project entry - do not add, remove, split, or merge bullets.
- Keep each rewritten bullet approximately the same length (word count) as the original it replaces.
- Do not add, remove, or reorder any role, project, or section.
- Do not invent experience, skills, projects, or qualifications that aren't in the master resume.
- The result must still fit on a single page when formatted the same way as the master resume - you are producing a drop-in replacement, not a longer or shorter document.

Output ONLY the tailored resume text - no commentary, no markdown code fences, no explanation of what you changed.
"""


def generate_tailored_resume(
    client: GeminiClient, master_resume_text: str, job: models.Job
) -> str:
    prompt = TAILOR_PROMPT_TEMPLATE.format(
        master_resume=master_resume_text,
        company=job.company,
        role_title=job.role_title,
        job_description=job.raw_job_description or "(no description available)",
    )
    return client.generate_text(prompt)
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd backend && venv/bin/pytest tests/test_tailoring.py -v`
Expected: all PASS

- [ ] **Step 5: Run the full test suite**

Run: `cd backend && venv/bin/pytest -q`
Expected: all PASS

- [ ] **Step 6: Commit**

```bash
git add backend/app/tailoring.py backend/tests/test_tailoring.py
git commit -m "feat: add Gemini-based tailored resume generation"
```

---

### Task 5: `crud.save_tailored_resume`

**Files:**
- Modify: `backend/app/crud.py`
- Test: `backend/tests/test_crud.py`

**Interfaces:**
- Consumes: `models.Job`, `models.Application`, `ALLOWED_TRANSITIONS`, `InvalidStatusTransition` (all existing)
- Produces: `crud.save_tailored_resume(db, job: models.Job, resume_text: str) -> models.Job`

- [ ] **Step 1: Write the failing tests**

Append to `backend/tests/test_crud.py`:

```python
def test_save_tailored_resume_first_save_transitions_new_to_tailored(db_session):
    job = crud.create_or_update_job(db_session, make_job_in())

    updated = crud.save_tailored_resume(db_session, job, "Tailored resume text")

    assert updated.status == JobStatus.tailored
    assert len(updated.applications) == 1
    assert updated.applications[0].tailored_resume_text == "Tailored resume text"


def test_save_tailored_resume_regenerate_when_already_tailored(db_session):
    job = crud.create_or_update_job(db_session, make_job_in())
    crud.save_tailored_resume(db_session, job, "First draft")

    updated = crud.save_tailored_resume(db_session, job, "Second draft")

    assert updated.status == JobStatus.tailored
    assert len(updated.applications) == 1  # updated in place, not duplicated
    assert updated.applications[0].tailored_resume_text == "Second draft"


def test_save_tailored_resume_rejects_applied_job(db_session):
    job = crud.create_or_update_job(db_session, make_job_in())
    crud.update_job_status(db_session, job, JobStatus.tailored)
    crud.mark_applied(db_session, job, applied_date=date(2026, 8, 21))

    with pytest.raises(crud.InvalidStatusTransition):
        crud.save_tailored_resume(db_session, job, "New draft")
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd backend && venv/bin/pytest tests/test_crud.py -v -k save_tailored_resume`
Expected: FAIL with `AttributeError: module 'app.crud' has no attribute 'save_tailored_resume'`

- [ ] **Step 3: Implement `crud.save_tailored_resume`**

Add to `backend/app/crud.py`, after `mark_applied`:

```python
def save_tailored_resume(db: Session, job: models.Job, resume_text: str) -> models.Job:
    if job.status not in (models.JobStatus.new, models.JobStatus.tailored):
        raise InvalidStatusTransition(
            f"Cannot save a tailored resume for job {job.id} in status {job.status.value}"
        )

    application = (
        db.query(models.Application)
        .filter(models.Application.job_id == job.id)
        .order_by(models.Application.id.desc())
        .first()
    )
    if application is None:
        application = models.Application(job_id=job.id)
        db.add(application)

    application.tailored_resume_text = resume_text

    if job.status == models.JobStatus.new:
        job.status = models.JobStatus.tailored

    db.commit()
    db.refresh(job)
    return job
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd backend && venv/bin/pytest tests/test_crud.py -v`
Expected: all PASS

- [ ] **Step 5: Run the full test suite**

Run: `cd backend && venv/bin/pytest -q`
Expected: all PASS

- [ ] **Step 6: Commit**

```bash
git add backend/app/crud.py backend/tests/test_crud.py
git commit -m "feat: add crud.save_tailored_resume with idempotent regenerate handling"
```

---

### Task 6: Tailoring endpoints on the jobs router

**Files:**
- Modify: `backend/app/schemas.py`
- Modify: `backend/app/routers/jobs.py`
- Test: `backend/tests/test_tailor_api.py`

**Interfaces:**
- Consumes: `tailoring.generate_tailored_resume` (Task 4), `crud.get_master_resume`, `crud.save_tailored_resume` (Tasks 2/5), `discovery.gemini_client.GeminiClient`/`GeminiError` (Task 1 / sub-project 2)
- Produces: `POST /jobs/{id}/tailor/generate` → `{"draft": str}`, `POST /jobs/{id}/tailor` → `JobOut`, `app.routers.jobs.get_gemini_client` (FastAPI dependency, overridable in tests)

- [ ] **Step 1: Add request/response schemas**

In `backend/app/schemas.py`, add:

```python
class TailorGenerateResponse(BaseModel):
    draft: str


class TailorSaveRequest(BaseModel):
    resume_text: str
```

- [ ] **Step 2: Write the failing endpoint tests**

Create `backend/tests/test_tailor_api.py`:

```python
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
    crud.update_job_status(db, job, JobStatus.tailored)
    crud.mark_applied(db, job, applied_date=date(2026, 8, 20))
    db.close()

    response = test_client.post(
        f"/jobs/{job.id}/tailor", json={"resume_text": "New text"}
    )
    assert response.status_code == 409
```

- [ ] **Step 3: Run the tests to verify they fail**

Run: `cd backend && venv/bin/pytest tests/test_tailor_api.py -v`
Expected: FAIL (endpoints/`get_gemini_client` don't exist yet — 404s on unknown routes)

- [ ] **Step 4: Add the dependency and endpoints to the router; remove the old `/resume` endpoint**

In `backend/app/routers/jobs.py`, replace the imports at the top:

```python
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from .. import crud, models, schemas
from ..database import get_db
```

with:

```python
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from discovery.gemini_client import GeminiClient, GeminiError
from .. import crud, models, schemas
from ..database import get_db
from ..tailoring import generate_tailored_resume
```

Update the docstring comment in `_to_job_out` (which currently mentions `tailored_resume_path`) to say `tailored_resume_text`, matching what Task 2 Step 7 already fixed in the body.

Replace the `GET /{job_id}/resume` endpoint at the bottom of the file:

```python
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

with:

```python
_gemini_client: GeminiClient | None = None


def get_gemini_client() -> GeminiClient:
    global _gemini_client
    if _gemini_client is None:
        _gemini_client = GeminiClient()
    return _gemini_client


@router.post("/{job_id}/tailor/generate", response_model=schemas.TailorGenerateResponse)
def generate_tailor_draft(
    job_id: int,
    db: Session = Depends(get_db),
    gemini_client: GeminiClient = Depends(get_gemini_client),
):
    job = crud.get_job(db, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")

    master_resume = crud.get_master_resume(db)
    if master_resume is None:
        raise HTTPException(
            status_code=404,
            detail="No master resume loaded - run load_resume.py first",
        )

    try:
        draft = generate_tailored_resume(gemini_client, master_resume.content, job)
    except GeminiError as exc:
        raise HTTPException(status_code=502, detail=str(exc))

    return schemas.TailorGenerateResponse(draft=draft)


@router.post("/{job_id}/tailor", response_model=schemas.JobOut)
def save_tailor_draft(
    job_id: int, payload: schemas.TailorSaveRequest, db: Session = Depends(get_db)
):
    job = crud.get_job(db, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")

    try:
        updated = crud.save_tailored_resume(db, job, payload.resume_text)
    except crud.InvalidStatusTransition as exc:
        raise HTTPException(status_code=409, detail=str(exc))

    return _to_job_out(updated)
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `cd backend && venv/bin/pytest tests/test_tailor_api.py -v`
Expected: all PASS

- [ ] **Step 6: Run the full test suite**

Run: `cd backend && venv/bin/pytest -q`
Expected: all PASS

- [ ] **Step 7: Commit**

```bash
git add backend/app/schemas.py backend/app/routers/jobs.py backend/tests/test_tailor_api.py
git commit -m "feat: add tailor generate/save endpoints, remove unused PDF resume endpoint"
```

---

### Task 7: Frontend — generate/save tailored resume on the job detail page

**Files:**
- Modify: `frontend/src/api/client.ts`
- Modify: `frontend/src/components/JobDetail.tsx`

**Interfaces:**
- Consumes: `POST /jobs/{id}/tailor/generate`, `POST /jobs/{id}/tailor` (Task 6)
- Produces: `generateTailoredResume(id) -> Promise<{ draft: string }>`, `saveTailoredResume(id, resumeText) -> Promise<Job>` in `api/client.ts`

- [ ] **Step 1: Add the field and API functions to `client.ts`**

In `frontend/src/api/client.ts`, add `tailored_resume_text: string | null;` to the `Job` interface (after `notes?: string | null;`):

```typescript
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
  applied_date?: string | null;
  application_number?: string | null;
  notes?: string | null;
  tailored_resume_text: string | null;
}
```

At the end of the file, add:

```typescript
export async function generateTailoredResume(
  id: number
): Promise<{ draft: string }> {
  const res = await fetch(`${API_BASE}/jobs/${id}/tailor/generate`, {
    method: "POST",
  });
  if (!res.ok)
    throw new Error(await extractErrorMessage(res, "Failed to generate tailored resume"));
  return res.json();
}

export async function saveTailoredResume(
  id: number,
  resumeText: string
): Promise<Job> {
  const res = await fetch(`${API_BASE}/jobs/${id}/tailor`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ resume_text: resumeText }),
  });
  if (!res.ok)
    throw new Error(await extractErrorMessage(res, "Failed to save tailored resume"));
  return res.json();
}
```

- [ ] **Step 2: Update `JobDetail.tsx`**

Replace the full contents of `frontend/src/components/JobDetail.tsx`:

```tsx
// frontend/src/components/JobDetail.tsx
import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import { Descriptions, Button, Space, message, Input } from "antd";
import {
  fetchJob,
  updateJobStatus,
  generateTailoredResume,
  saveTailoredResume,
} from "../api/client";
import type { Job } from "../api/client";
import MarkAppliedModal from "./MarkAppliedModal";

const { TextArea } = Input;

export default function JobDetail() {
  const { id } = useParams();
  const [job, setJob] = useState<Job | null>(null);
  const [modalOpen, setModalOpen] = useState(false);
  const [draft, setDraft] = useState("");
  const [generating, setGenerating] = useState(false);
  const [saving, setSaving] = useState(false);

  const load = () => {
    if (!id) return;
    fetchJob(Number(id))
      .then((fetched) => {
        setJob(fetched);
        setDraft(fetched.tailored_resume_text ?? "");
      })
      .catch((err) =>
        message.error(err instanceof Error ? err.message : "Failed to load job")
      );
  };

  useEffect(load, [id]);

  if (!job) return null;

  const handleIgnore = async () => {
    try {
      await updateJobStatus(job.id, "ignored");
      message.success("Job marked ignored");
      load();
    } catch (err) {
      message.error(err instanceof Error ? err.message : "Failed to update job");
    }
  };

  const handleReject = async () => {
    try {
      await updateJobStatus(job.id, "rejected");
      message.success("Job marked rejected");
      load();
    } catch (err) {
      message.error(err instanceof Error ? err.message : "Failed to update job");
    }
  };

  const handleGenerate = async () => {
    setGenerating(true);
    try {
      const { draft: generated } = await generateTailoredResume(job.id);
      setDraft(generated);
      message.success("Draft generated - review and save below");
    } catch (err) {
      message.error(
        err instanceof Error ? err.message : "Failed to generate tailored resume"
      );
    } finally {
      setGenerating(false);
    }
  };

  const handleSave = async () => {
    setSaving(true);
    try {
      await saveTailoredResume(job.id, draft);
      message.success("Tailored resume saved");
      load();
    } catch (err) {
      message.error(
        err instanceof Error ? err.message : "Failed to save tailored resume"
      );
    } finally {
      setSaving(false);
    }
  };

  // Mirrors backend ALLOWED_TRANSITIONS: new, tailored, and applied can all
  // transition to rejected.
  const canReject =
    job.status === "new" || job.status === "tailored" || job.status === "applied";
  const canTailor = job.status === "new" || job.status === "tailored";

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
        {job.status === "applied" && (
          <>
            <Descriptions.Item label="Applied Date">
              {job.applied_date ?? "—"}
            </Descriptions.Item>
            <Descriptions.Item label="Application Number">
              {job.application_number ?? "—"}
            </Descriptions.Item>
            <Descriptions.Item label="Notes">{job.notes ?? "—"}</Descriptions.Item>
          </>
        )}
      </Descriptions>

      {canTailor && (
        <div style={{ margin: "16px 0" }}>
          <Space style={{ marginBottom: 8 }}>
            <Button loading={generating} onClick={handleGenerate}>
              Generate Tailored Resume
            </Button>
            <Button type="primary" loading={saving} disabled={!draft} onClick={handleSave}>
              Save
            </Button>
          </Space>
          <TextArea
            rows={20}
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            placeholder="Click Generate to draft a tailored resume, or paste/edit your own here before saving."
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
        {canReject && (
          <Button danger onClick={handleReject}>
            Reject
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

- [ ] **Step 3: Type-check the frontend**

Run: `cd frontend && npm run build`
Expected: builds successfully with no TypeScript errors

- [ ] **Step 4: Manual click-through verification**

With the backend running (`cd backend && venv/bin/uvicorn app.main:app --reload`) and frontend running (`cd frontend && npm run dev`), and at least one `new` job in the database (seed one with `venv/bin/python seed.py` if needed) and a master resume loaded (Task 3/8):

1. Open a `new` job's detail page.
2. Click "Generate Tailored Resume" — confirm the textarea fills with generated text and a success message appears.
3. Edit the text in the textarea.
4. Click "Save" — confirm a success message appears, the page reloads the job, and the status badge now shows `tailored`.
5. Reload the page — confirm the textarea still shows the saved (edited) text, not a blank box.
6. Try generating again on the now-`tailored` job — confirm it still works and Save still succeeds (the regenerate path).

- [ ] **Step 5: Commit**

```bash
git add frontend/src/api/client.ts frontend/src/components/JobDetail.tsx
git commit -m "feat: add tailored resume generate/edit/save UI to job detail page"
```

---

### Task 8: End-to-end manual verification

**Files:** none (verification only)

**Interfaces:** none (uses everything from Tasks 1-7)

- [ ] **Step 1: Run the full automated test suite**

Run: `cd backend && venv/bin/pytest -v`
Expected: all tests pass, including every test added in Tasks 1-6.

- [ ] **Step 2: Load the real master resume**

Run: `cd backend && venv/bin/python load_resume.py "/Users/parthmohan/Desktop/UMD/IMPORTANT DOCS/final_resume/Parth_Mohan.pdf"`
Expected: prints `Loaded master resume from ... (N characters).` with a plausible character count (a one-page resume is typically 2,000-4,000 characters of extracted text — investigate if it's near-zero, which would mean `pypdf` failed to extract text from that PDF).

- [ ] **Step 3: Generate a real tailored resume for a real job**

Start both servers (`uvicorn app.main:app --reload` in `backend/`, `npm run dev` in `frontend/`) and open a `new` job from Job Discovery's output (or `venv/bin/python seed.py` for a sample one) in the browser. Click "Generate Tailored Resume".

Expected: a tailored draft appears within the request timeout. Compare it side-by-side against the master resume:
- Same section headers, same order.
- Same number of bullets per role/project.
- No new sections, roles, or projects.
- No invented experience.
- Roughly the same total length (should still read as one page).

If the model violates any of these, note it — this is exactly what the editable-textarea review step exists to catch before saving; it's expected that an LLM won't get this perfect every time, but it should be close per the spec's prompt constraints.

- [ ] **Step 4: Save and confirm the status transition**

Click "Save". Confirm the job's status badge changes to `tailored` and reloading the page still shows the saved text.

- [ ] **Step 5: Confirm regeneration on an already-tailored job works**

On the same now-`tailored` job, click "Generate Tailored Resume" again, edit the new draft, and click "Save" again. Confirm no error occurs and the saved text updates (status stays `tailored`, not a transition error).
