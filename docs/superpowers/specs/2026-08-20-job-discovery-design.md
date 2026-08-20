# Job Discovery — Design

## Context

ApplicationBot is a locally-running platform (macOS) that helps the user
(a University of Maryland CS student targeting Summer 2027 AI
engineering, ML engineering, and SWE internships) discover relevant
internship postings, generate tailored resume copies per posting, and
track application status — with native macOS notifications when new
postings are found.

Sub-project 1, **Job Intake & Tracking Core**, is complete and merged
(PR #1): it provides a SQLite database (`jobs`/`applications` tables), a
FastAPI backend, and a React+antd dashboard. Jobs are tracked through a
status lifecycle (`new` → `tailored` → `applied` → `rejected`/`ignored`),
with `app.crud.create_or_update_job` already implementing upsert
semantics keyed on `(company, role_title, source_url)`.

This document covers **sub-project 3: Job Discovery** — the piece that
actually finds real internship postings and writes them into the
tracker as `new` jobs. It's the second sub-project built (after Job
Intake & Tracking Core), ahead of Resume Tailoring and Application
Staging, both of which depend on Discovery finding real jobs to act on.

## Non-goals

- No automated application submission (established in sub-project 1;
  unaffected by this sub-project).
- No resume tailoring — that's sub-project 2/4 (Resume Tailoring,
  Application Staging). Discovery only writes `new` jobs; it never sets
  status to `tailored`.
- No UI changes — Discovery is a backend-only batch process; postings it
  writes appear in the existing dashboard automatically.
- Not attempting full coverage of every possible internship source on
  day one — four source types are in scope for this sub-project (see
  below); more can be added later since the adapter architecture is
  designed to make that additive.

## Source types in scope

Four adapters, each producing normalized postings that flow into one
shared classification/filter/write pipeline:

1. **Curated GitHub lists** — `SimplifyJobs/Summer2027-Internships` and
   `vanshb03/Summer2027-Internships`. Structured data (a `listings.json`
   feed if available, falling back to parsing the README's markdown
   table), filtered to Software Engineering and Data Science/AI/ML
   categories. No LLM needed for extraction — the data is already
   structured.
2. **Job board APIs** — for each company in a configured list, hit that
   company's public Greenhouse (`boards-api.greenhouse.io`) or Lever
   (`api.lever.co`) JSON endpoint. Structured data, no LLM needed for
   extraction.
3. **General web search** — Google Programmable Search (Custom Search
   JSON API) queries for candidate posting pages matching the user's
   criteria, followed by fetching each result page and using **Gemini
   to extract** company/role/description from the raw page content
   (search results are links/snippets, not structured postings).
4. **Company career pages** — for a configured list of companies, fetch
   their career page and use **Gemini to extract** postings from the
   raw HTML. Chosen over hand-written per-company CSS selectors because
   selectors are fragile against the dozens of different page layouts
   in a company list and break silently on redesigns; a single LLM
   extraction prompt generalizes across layouts.

The job-board and career-page company list starts as a seeded default
(~20-30 well-known companies posting AI/ML/SWE internships) that the
user can edit afterward in `backend/discovery/companies.yaml`.

## Architecture

- **Entry point**: `backend/discover.py`, invoked by a macOS `launchd`
  job on a periodic schedule (per sub-project 1's design). Each run:
  load config → run all 4 adapters sequentially → normalize → classify
  each posting via Gemini → write postings that pass filtering via
  `create_or_update_job` → log a run summary (found / passed filter /
  written).
- Adapters run sequentially rather than in parallel — this stays polite
  to external APIs/sites and keeps run logs straightforward to read;
  performance is not a concern at this scale (a handful of sources,
  once per scheduled run).
- **New package**: `backend/discovery/`, alongside the existing
  `backend/app/`:
  - `discovery/adapters/base.py` — `Adapter` interface with one method,
    `fetch() -> list[RawPosting]`
  - `discovery/adapters/github_list.py` — parametrized by repo; used
    twice (SimplifyJobs, vanshb03)
  - `discovery/adapters/job_board.py` — parametrized by company list +
    board type (`greenhouse`/`lever`)
  - `discovery/adapters/web_search.py` — Google Custom Search query +
    Gemini extraction
  - `discovery/adapters/career_page.py` — company list + Gemini
    extraction
  - `discovery/classifier.py` — the shared Gemini classification/filter
    step (open? Summer 2027? paid? US? sophomore/junior-eligible?)
  - `discovery/pipeline.py` — orchestrates adapters → classifier →
    `crud.create_or_update_job`, with per-adapter error isolation and
    fuzzy cross-source dedup
  - `discovery/config.py` — loads `companies.yaml` and search query
    templates
  - `discovery/gemini_client.py` — thin wrapper around the Gemini API,
    reused by the classifier and the two extraction adapters
- **Config**: `backend/discovery/companies.yaml` (seeded company list),
  `.env` for `GEMINI_API_KEY` and the Google Custom Search API
  key/CX id — both needed by this sub-project (moved up from the
  originally-planned Resume Tailoring sub-project, since discovery's
  filtering step requires Gemini).

## Data flow

```
Adapter.fetch() → RawPosting[] → normalize → Gemini classify/filter
  → fuzzy cross-source dedup check → crud.create_or_update_job()
```

A `RawPosting` carries: company, role_title, source (adapter name),
source_url, location, raw_description, posted_date (if known). The
classifier consumes `raw_description` and returns a verdict (pass/fail)
plus the structured fields (`eligibility`, `paid`) that
`create_or_update_job` needs — these map directly onto the existing
`jobs` table schema from sub-project 1.

## Error handling

- **Per-adapter isolation**: each adapter call is wrapped in its own
  try/except in the pipeline. One adapter failing (site down, invalid
  API key, a list's format changed) logs the error and the run
  continues with the other three.
- **Gemini call failures** (rate limit, timeout, malformed response):
  retried once with backoff; if it still fails, that posting is skipped
  for this run — not written, not marked as permanently failed — and
  naturally retried next run when the source is re-fetched, since
  re-discovery is idempotent via the existing upsert.
- **Rate limiting**: both the free Gemini tier and the Google Custom
  Search free tier (100 queries/day) are capped. The pipeline sleeps
  briefly between Gemini calls and caps web-search queries per run
  (configurable, conservative default) so a single run can't exhaust a
  day's quota.
- **Malformed/unexpected source data** (a GitHub list's JSON schema
  changes, a career page returns a CAPTCHA/block page): logged with the
  raw snippet for debugging, posting skipped, run continues.
- **Cross-source duplicate detection**: the existing
  `(company, role_title, source_url)` uniqueness only dedupes exact
  `source_url` matches, but the same posting can appear on a GitHub
  list, a job board, and a career page under three different URLs.
  Before writing, the pipeline runs a secondary fuzzy check (normalized
  `company` + normalized `role_title` match against existing `new` or
  `tailored` jobs) and skips writing if a close match from a different
  source already exists.

## Testing

- **Adapter tests**: each adapter tested against a saved fixture (a
  captured `listings.json` snippet, a Greenhouse API response sample, a
  saved search-result HTML page, a saved career-page HTML snippet) —
  not live network calls. Fast, deterministic, no API costs in CI.
- **Classifier/extraction tests**: use a fake/mocked Gemini client
  returning canned responses, verifying the pipeline correctly applies
  what the model returns (fields extracted, filter logic applied) — not
  asserting on the model's own judgment quality, which a unit test
  can't meaningfully verify.
- **Pipeline tests**: verify orchestration behavior directly — one
  adapter raising doesn't stop the others, a posting failing
  classification isn't written, a duplicate (exact or fuzzy match from
  a different source) isn't double-written.
- **Manual verification**: one real end-to-end run against live sources
  (using the user's real API keys), inspecting what actually got
  written to confirm filter quality in practice.
