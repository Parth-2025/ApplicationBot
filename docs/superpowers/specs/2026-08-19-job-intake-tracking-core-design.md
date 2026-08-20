# Job Intake & Tracking Core — Design

## Context

ApplicationBot is a locally-running platform (macOS) that helps the user
(a University of Maryland CS student targeting Summer 2027 AI
engineering, ML engineering, and SWE internships) discover relevant
internship postings, generate tailored resume copies per posting, and
track application status — with native macOS notifications when new
postings are found.

The full platform decomposes into five sub-projects, each with its own
design/spec/implementation cycle:

1. **Job intake & tracking core** (this document) — data model, storage,
   and dashboard that all other sub-projects plug into
2. Resume tailoring engine
3. Job discovery
4. Application staging (manual-submit workflow, not auto-apply)
5. Notification system

This document covers sub-project 1 only.

## Non-goals (platform-wide, informing this design)

- **No automated application submission.** ATS platforms (Workday,
  Greenhouse, Lever, iCIMS, etc.) vary widely, often have bot detection,
  and auto-submission risks ToS violations and broken submissions.
  Instead: the system discovers postings, tailors a resume copy, and
  notifies the user, who submits manually. Because of this, fields like
  `applied_date` and `application_number` cannot be captured
  automatically — the tracking core must support the user marking an
  application as submitted after the fact.
- No multi-user support, no auth, no external network exposure — this
  is a single-user local tool bound to `localhost`.

## Data model

SQLite database, two primary tables.

### `jobs`

| Column | Type | Notes |
|---|---|---|
| id | integer PK | |
| company | text | |
| role_title | text | |
| source | text | which site/feed the posting came from |
| source_url | text | link to the original posting |
| location | text | |
| paid | boolean | must be true per discovery filter, stored for display |
| eligibility | enum | `soph_junior`, `all_levels`, `freshman_only`, `senior_only`, `other` — discovery filters to `soph_junior`/`all_levels` only |
| posted_date | date, nullable | date posting went live, if known |
| discovered_date | date | when ApplicationBot found it |
| status | enum | `new` → `tailored` → `applied` → `rejected` / `ignored` |
| raw_job_description | text | full JD text, used by tailoring engine |

Uniqueness constraint on `(company, role_title, source_url)` to prevent
duplicate rows when the same posting is seen again on a later discovery
run or via multiple sources. A re-seen posting updates
`discovered_date` and refreshes fields rather than inserting a new row.

### `applications`

| Column | Type | Notes |
|---|---|---|
| id | integer PK | |
| job_id | integer FK → jobs.id | |
| tailored_resume_path | text, nullable | path to generated PDF, set once tailoring runs |
| contact_email | text, nullable | if known from the posting |
| applied_date | date, nullable | set by user via mark-applied action |
| application_number | text, nullable | optional, user-entered if the portal provided one |
| notes | text, nullable | freeform |

## Architecture

- **Backend**: FastAPI app backed by SQLite via SQLAlchemy. Chosen over
  Flask because a separate React frontend needs a clean JSON API, and
  FastAPI's Pydantic models + auto-generated OpenAPI docs help as the
  API surface grows to support later sub-projects.
- **Frontend**: React + antd (Ant Design components), served locally.
  - Job list: antd `Table` with built-in filter/sort over company,
    role, status, eligibility, discovered date
  - Job detail: `Drawer` or page using `Descriptions` for job info,
    embedded PDF viewer for the tailored resume, link to source posting
  - Mark-applied: `Button` + `Modal` with a date picker and optional
    application number / notes fields
  - Manual status override: mark a job `ignored`/`rejected`
- **Endpoints** (initial set):
  - `GET /jobs` — list with filters
  - `GET /jobs/{id}` — detail
  - `PATCH /jobs/{id}` — status transitions, mark-applied fields
  - `GET /jobs/{id}/resume` — serves the tailored PDF
- Discovery and tailoring (later sub-projects) run as local background
  jobs and write to the same SQLite DB directly / via shared internal
  functions — they do not need to go through the REST API.
- Bound to `localhost` only; no auth, no external exposure.

## Error handling

- Pydantic models validate API input; invalid status transitions (e.g.
  marking a `new` job `applied` without it being `tailored` first)
  return 4xx with a clear message.
- SQLite writes wrapped in transactions. A duplicate
  `(company, role_title, source_url)` insert is treated as an update
  (refresh `discovered_date`/fields) rather than erroring.
- Frontend surfaces API errors via antd `message`/`notification`
  components rather than failing silently.

## Testing

- Backend: pytest unit tests for CRUD operations and status-transition
  validation, using an in-memory SQLite DB.
- Frontend: manual verification is acceptable given the single-user,
  small-scope nature of this tool; no dedicated component test suite
  planned.
