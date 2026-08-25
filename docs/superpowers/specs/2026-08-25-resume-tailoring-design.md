# Resume Tailoring Assist — Design

## Context

ApplicationBot is a locally-running platform (macOS) that helps the user
(a University of Maryland CS student targeting Summer 2027 AI
engineering, ML engineering, and SWE internships) discover relevant
internship postings, generate tailored resume copies per posting, and
track application status.

Sub-project 1, **Job Intake & Tracking Core**, and sub-project 2, **Job
Discovery**, are both complete and merged: the tracker has a SQLite
database (`jobs`/`applications` tables), a FastAPI backend, a React+antd
dashboard, and a discovery pipeline that finds and writes real postings
as `new` jobs. Jobs move through a status lifecycle
(`new` → `tailored` → `applied` → `rejected`/`ignored`).

This document covers **sub-project 3: Resume Tailoring Assist** — the
piece that helps the user produce a tailored resume for a specific job
and move it from `new` to `tailored`. It depends on Job Discovery having
already found jobs to tailor for.

## Non-goals

- No automated application submission — unaffected by this sub-project.
- No cover letter generation — resume only.
- No PDF generation or visual/styled output — the feature produces
  plain text/markdown that the user pastes into their own resume
  template to produce the final PDF themselves.
- No resume-content authoring — the feature only rewords/reorders
  existing master-resume content for relevance; it never invents
  experience, projects, or skills the user doesn't already have.

## The one-page constraint (critical)

The user's real resume is a single page. A tailored version must **drop
in as a replacement** for that one page — same sections, same order,
same number of bullets per entry, comparable length per bullet — with
only wording changed (emphasis, keyword alignment, verb choice) to suit
the target job. The model must never add sections, add/remove
roles/projects, expand a bullet into multiple bullets, or otherwise
change the resume's structure or length. This is a hard constraint on
the generation prompt (see Components below), not a suggestion.

## Architecture

Three new pieces, reusing existing infrastructure (the Gemini client
from sub-project 2, the FastAPI app, the React frontend) rather than
building parallel systems:

1. **Master resume storage** — one `MasterResume` row holding the user's
   resume as extracted plain text, loaded once via a CLI script and
   re-loaded manually whenever the real resume changes.
2. **Tailoring generation** — a Gemini call that takes the master resume
   text + a job's details and returns tailored resume text, enforcing
   the one-page/same-structure constraint via the prompt.
3. **Two new endpoints** on the existing jobs router: generate a draft
   (not persisted), and save a (possibly user-edited) draft, which
   persists it and transitions the job's status.

## Components

### `backend/app/models.py`

- New `MasterResume` table: `id`, `content: Text`, `updated_date: Date`.
  Single-row table — the ingest script upserts row `id=1`.
- `Application.tailored_resume_path` is renamed to
  `tailored_resume_text: Text`. This column exists today but nothing
  writes to it yet (it was scaffolded ahead of this sub-project), so
  this is a rename, not a migration of real data.

### `backend/load_resume.py`

CLI script, parallel to `seed.py`/`discover.py`:

```
venv/bin/python load_resume.py <path-to-resume.pdf>
```

Extracts text via `pypdf` and upserts it into `MasterResume` via a new
`crud.save_master_resume(db, content) -> MasterResume`. Also add
`crud.get_master_resume(db) -> MasterResume | None`.

### `backend/app/tailoring.py`

```python
def generate_tailored_resume(client: GeminiClient, master_resume_text: str, job: Job) -> str
```

Builds a prompt containing:
- The full master resume text.
- The job's company, role title, and raw job description.
- Explicit structural constraints: preserve section headers, their
  order, and the number of bullets per role/project exactly as in the
  master resume; keep each rewritten bullet within roughly the same
  line length as the original; do not add, remove, or reorder sections
  or entries; only change wording to emphasize relevance to this job.
- An instruction to output only the tailored resume text (no
  commentary, no markdown fences).

Reuses `discovery.gemini_client.GeminiClient` for the actual call
(rate-limiting, timeouts, retries already handled there — no new
Gemini-calling code needed). Returns the raw text response; raises
`GeminiError`/`GeminiQuotaExhaustedError` on failure (same exceptions
sub-project 2 already defines), which the endpoint translates into an
HTTP error.

### `backend/app/crud.py`

- `save_tailored_resume(db, job, resume_text) -> Job`: finds the job's
  latest `Application` (creating one if none exists — same pattern
  `mark_applied` already uses), sets `tailored_resume_text`, and:
  - if `job.status == JobStatus.new`, transitions it to `tailored` via
    the existing `update_job_status`.
  - if `job.status == JobStatus.tailored` already (regenerating), just
    updates the text — no status transition attempted, since
    `tailored → tailored` isn't in `ALLOWED_TRANSITIONS` and would
    raise `InvalidStatusTransition`.
  - any other status (`applied`/`rejected`/`ignored`) raises
    `InvalidStatusTransition` — tailoring only applies to jobs still in
    or entering the `new`/`tailored` stage.

### `backend/app/routers/jobs.py`

- `POST /jobs/{id}/tailor/generate` — loads the master resume (404 with
  a clear "no master resume loaded — run load_resume.py" message if
  none exists), calls `tailoring.generate_tailored_resume`, returns
  `{"draft": text}`. Does not persist anything.
- `POST /jobs/{id}/tailor` — body `{"resume_text": str}` — calls
  `crud.save_tailored_resume`, returns the updated `JobOut`.
- Remove `GET /jobs/{id}/resume` (the FileResponse/PDF download
  endpoint) — dead code once `tailored_resume_path` is gone; the text
  is now returned directly on `JobOut.tailored_resume_text` for display,
  and the frontend can offer a client-side text-file download from data
  it already has, with no separate backend endpoint needed.

### `backend/app/schemas.py`

- `JobOut.tailored_resume_path` → `tailored_resume_text: Optional[str]`.
- New `TailorGenerateResponse { draft: str }` and
  `TailorSaveRequest { resume_text: str }`.

### Frontend (`frontend/src/`)

Job detail page:
- "Generate Tailored Resume" button (only shown when the job has a
  `raw_job_description` and status is `new` or `tailored`) — calls the
  generate endpoint, shows the draft in an editable `<textarea>`.
- "Save" button — calls the save endpoint with the (possibly edited)
  textarea contents; on success, refreshes the job so the status badge
  and stored text reflect the save.
- If `tailored_resume_text` already exists on the job, the textarea is
  pre-filled with it on page load (so re-opening a tailored job shows
  what was saved, not a blank box).

## Data flow

```
MasterResume.content (loaded once via load_resume.py)
  + Job.raw_job_description, company, role_title
  → tailoring.generate_tailored_resume() [Gemini call]
  → draft text returned to frontend (not saved)
  → user reviews/edits in the browser
  → POST /jobs/{id}/tailor
  → crud.save_tailored_resume() → Application.tailored_resume_text + Job.status
```

## Error handling

- **No master resume loaded**: `/tailor/generate` returns 404 with a
  message telling the user to run `load_resume.py`. The frontend
  surfaces this via its existing pattern of showing backend error
  detail messages.
- **Gemini call failure** (timeout, quota exhausted, malformed
  response): `/tailor/generate` returns a 502 with the underlying
  error's message; nothing is persisted, so the user can just retry.
  Unlike sub-project 2's pipeline, there's no "skip and retry next run"
  fallback here — this is a synchronous, user-initiated action, so the
  error surfaces immediately.
- **Invalid status transition** (tailoring a job that's `applied`,
  `rejected`, or `ignored`): `/tailor` returns 409, same pattern as the
  existing status-update endpoint.
- **Structural drift in the model's output** (it added a section, wrote
  two pages' worth of content, etc.): not automatically detected — the
  user reviews the draft in the editable textarea before saving, which
  is the actual safety net for the one-page constraint. The prompt-level
  instructions reduce how often this happens; they can't guarantee it.

## Testing

- **`tailoring.generate_tailored_resume` unit tests**: fake Gemini
  client (same pattern as sub-project 2's `FakeClassifierClient`)
  verifying the prompt includes the master resume, job details, and the
  structural-preservation instructions, and that the function returns
  the client's response text.
- **`crud.save_tailored_resume` tests**: covers first save (`new` →
  `tailored`, creates an `Application`), re-save on an already-
  `tailored` job (text updates, no transition attempted, no error), and
  rejection when the job is `applied`/`rejected`/`ignored`.
- **Endpoint tests**: `TestClient` with a monkeypatched Gemini client —
  generate returns a draft without touching the DB; save persists and
  updates status; 404 when no master resume is loaded; 409 on invalid
  transition.
- **`load_resume.py` test**: given a fixture PDF (or a monkeypatched
  extraction function), verifies it upserts a single `MasterResume` row
  and that re-running it with new content replaces rather than
  duplicates the row.
