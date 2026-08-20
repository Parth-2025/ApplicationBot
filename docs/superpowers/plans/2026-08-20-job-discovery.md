# Job Discovery Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a pluggable source-adapter pipeline that finds real Summer 2027 AI/ML/SWE internship postings from four source types (curated GitHub lists, job-board APIs, web search, company career pages), classifies/filters them via Gemini, and writes passing postings into the existing `jobs` table via `app.crud.create_or_update_job`.

**Architecture:** Four independent `Adapter` implementations each produce a list of normalized `RawPosting` objects. A single shared pipeline (`discovery/pipeline.py`) runs each adapter with error isolation, sends every posting through one Gemini-based classifier, applies a fuzzy cross-source dedup check, and writes postings that pass through the existing CRUD layer. An entry point script (`backend/discover.py`) is invoked by a macOS `launchd` job on a schedule.

**Tech Stack:** Python (extends the existing `backend/` FastAPI project), `httpx` (already a dependency) for HTTP, `beautifulsoup4` for HTML-to-text extraction, `pyyaml` for company config, `google-generativeai` for Gemini, `python-dotenv` for `.env` loading, `pytest` for tests.

**Spec:** docs/superpowers/specs/2026-08-20-job-discovery-design.md

**Prerequisite:** This plan assumes PR #1 (Job Intake & Tracking Core) is merged to `main` and this work starts from a fresh worktree/branch based on `main` at that point — `backend/app/{database,models,schemas,crud}.py` and the existing `backend/tests/` suite must already exist and pass before Task 1 begins.

## Global Constraints

- No automated application submission — this sub-project only ever writes jobs with `status = new` (the default); it never sets `status = tailored` or `applied`.
- `jobs` table uniqueness is `(company, role_title, source_url)`, already enforced by `app.crud.create_or_update_job`, which upserts on match — reuse it, don't reimplement it.
- `eligibility` values are exactly: `soph_junior`, `all_levels`, `freshman_only`, `senior_only`, `other` (matches `app.models.Eligibility`).
- Only jobs classified as: still open, Summer 2027, paid, US-based, eligible to `soph_junior` or `all_levels`, and role-relevant (SWE/AI/ML) get written.
- Per-adapter error isolation: one adapter failing must not stop the others or crash the run.
- Gemini and Google Custom Search calls must be rate-limited (sleep between calls; cap search queries per run) to respect free-tier daily quotas.
- Backend testing: pytest, no live network calls in the automated suite — adapters are tested against saved fixtures, Gemini calls against a fake/mocked client.
- Curated GitHub sources: `SimplifyJobs/Summer2027-Internships` and `vanshb03/Summer2027-Internships`, both fetched via their `.github/scripts/listings.json` feed.

---

### Task 1: Discovery package scaffolding and config loading

**Files:**
- Create: `backend/discovery/__init__.py`
- Create: `backend/discovery/config.py`
- Create: `backend/discovery/companies.yaml`
- Create: `backend/.env.example`
- Modify: `backend/requirements.txt`
- Create: `backend/tests/discovery/__init__.py`
- Test: `backend/tests/discovery/test_config.py`

**Interfaces:**
- Produces: `discovery.config.CompanyBoardConfig` (dataclass: `name: str`, `board_type: str`, `board_slug: str`), `discovery.config.CareerPageConfig` (dataclass: `name: str`, `url: str`), `discovery.config.load_company_boards(path: Path = COMPANIES_FILE) -> list[CompanyBoardConfig]`, `discovery.config.load_career_pages(path: Path = COMPANIES_FILE) -> list[CareerPageConfig]`, `discovery.config.load_search_queries(path: Path = COMPANIES_FILE) -> list[str]`, `discovery.config.get_gemini_api_key() -> str`, `discovery.config.get_gemini_model_name() -> str`, `discovery.config.get_google_search_config() -> tuple[str, str]` (returns `(api_key, cx)`)

- [ ] **Step 1: Add new dependencies to requirements.txt**

```text
fastapi
uvicorn[standard]
sqlalchemy
pydantic
pytest
httpx
beautifulsoup4
pyyaml
google-generativeai
python-dotenv
```

Run: `cd backend && venv/bin/pip install -r requirements.txt`

- [ ] **Step 2: Create backend/.env.example**

```text
GEMINI_API_KEY=your-gemini-api-key-here
GEMINI_MODEL=gemini-2.0-flash
GOOGLE_SEARCH_API_KEY=your-google-custom-search-api-key-here
GOOGLE_SEARCH_CX=your-custom-search-engine-id-here
```

- [ ] **Step 3: Create backend/discovery/companies.yaml**

```yaml
companies:
  - name: "Stripe"
    board_type: greenhouse
    board_slug: stripe
  - name: "Robinhood"
    board_type: greenhouse
    board_slug: robinhood
  - name: "Coinbase"
    board_type: greenhouse
    board_slug: coinbase
  - name: "Asana"
    board_type: greenhouse
    board_slug: asana
  - name: "Affirm"
    board_type: greenhouse
    board_slug: affirm
  - name: "Pinterest"
    board_type: greenhouse
    board_slug: pinterest
  - name: "Airbnb"
    board_type: greenhouse
    board_slug: airbnb
  - name: "Figma"
    board_type: greenhouse
    board_slug: figma
  - name: "Discord"
    board_type: greenhouse
    board_slug: discord
  - name: "Databricks"
    board_type: greenhouse
    board_slug: databricks
  - name: "Brex"
    board_type: greenhouse
    board_slug: brex
  - name: "Instacart"
    board_type: greenhouse
    board_slug: instacart
  - name: "Cloudflare"
    board_type: greenhouse
    board_slug: cloudflare
  - name: "Twilio"
    board_type: greenhouse
    board_slug: twilio
  - name: "Dropbox"
    board_type: greenhouse
    board_slug: dropbox
  - name: "GitLab"
    board_type: greenhouse
    board_slug: gitlab
  - name: "Reddit"
    board_type: greenhouse
    board_slug: reddit
  - name: "Samsara"
    board_type: greenhouse
    board_slug: samsara
  - name: "Scale AI"
    board_type: greenhouse
    board_slug: scaleai
  - name: "Palantir"
    board_type: lever
    board_slug: palantir
  - name: "Zoox"
    board_type: lever
    board_slug: zoox

career_pages:
  - name: "Google"
    url: "https://www.google.com/about/careers/applications/jobs/results/?q=intern"
  - name: "Meta"
    url: "https://www.metacareers.com/jobs/?q=intern"
  - name: "Amazon"
    url: "https://www.amazon.jobs/en/search?base_query=intern"

search_queries:
  - "AI engineering intern Summer 2027 apply"
  - "machine learning engineer intern Summer 2027 apply"
  - "software engineer intern Summer 2027 sophomore junior apply"
  - "SWE intern Summer 2027 United States apply"
  - "AI ML intern Summer 2027 paid United States apply"
```

- [ ] **Step 4: Create backend/tests/discovery/__init__.py**

Empty file.

- [ ] **Step 5: Write the failing test for config**

```python
# backend/tests/discovery/test_config.py
import textwrap
import pytest
from discovery import config


SAMPLE_YAML = textwrap.dedent("""
    companies:
      - name: "Acme"
        board_type: greenhouse
        board_slug: acme
      - name: "Widgets Inc"
        board_type: lever
        board_slug: widgets

    career_pages:
      - name: "BigCo"
        url: "https://bigco.example.com/careers"

    search_queries:
      - "software engineer intern Summer 2027"
    """)


@pytest.fixture()
def sample_config_file(tmp_path):
    path = tmp_path / "companies.yaml"
    path.write_text(SAMPLE_YAML)
    return path


def test_load_company_boards(sample_config_file):
    boards = config.load_company_boards(sample_config_file)
    assert boards == [
        config.CompanyBoardConfig(name="Acme", board_type="greenhouse", board_slug="acme"),
        config.CompanyBoardConfig(name="Widgets Inc", board_type="lever", board_slug="widgets"),
    ]


def test_load_career_pages(sample_config_file):
    pages = config.load_career_pages(sample_config_file)
    assert pages == [
        config.CareerPageConfig(name="BigCo", url="https://bigco.example.com/careers"),
    ]


def test_load_search_queries(sample_config_file):
    queries = config.load_search_queries(sample_config_file)
    assert queries == ["software engineer intern Summer 2027"]


def test_get_gemini_api_key_missing_raises(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    with pytest.raises(RuntimeError):
        config.get_gemini_api_key()


def test_get_gemini_api_key_present(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "test-key-123")
    assert config.get_gemini_api_key() == "test-key-123"


def test_get_gemini_model_name_defaults(monkeypatch):
    monkeypatch.delenv("GEMINI_MODEL", raising=False)
    assert config.get_gemini_model_name() == "gemini-2.0-flash"


def test_get_gemini_model_name_override(monkeypatch):
    monkeypatch.setenv("GEMINI_MODEL", "gemini-custom")
    assert config.get_gemini_model_name() == "gemini-custom"


def test_get_google_search_config(monkeypatch):
    monkeypatch.setenv("GOOGLE_SEARCH_API_KEY", "search-key")
    monkeypatch.setenv("GOOGLE_SEARCH_CX", "cx-123")
    assert config.get_google_search_config() == ("search-key", "cx-123")


def test_get_google_search_config_missing_raises(monkeypatch):
    monkeypatch.delenv("GOOGLE_SEARCH_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_SEARCH_CX", raising=False)
    with pytest.raises(RuntimeError):
        config.get_google_search_config()
```

- [ ] **Step 6: Run test to verify it fails**

Run: `cd backend && venv/bin/pytest tests/discovery/test_config.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'discovery'`

- [ ] **Step 7: Write discovery/config.py**

```python
import os
from dataclasses import dataclass
from pathlib import Path

import yaml
from dotenv import load_dotenv

load_dotenv()

COMPANIES_FILE = Path(__file__).parent / "companies.yaml"


@dataclass
class CompanyBoardConfig:
    name: str
    board_type: str
    board_slug: str


@dataclass
class CareerPageConfig:
    name: str
    url: str


def _load_yaml(path: Path) -> dict:
    with open(path) as f:
        return yaml.safe_load(f) or {}


def load_company_boards(path: Path = COMPANIES_FILE) -> list[CompanyBoardConfig]:
    raw = _load_yaml(path)
    return [
        CompanyBoardConfig(
            name=c["name"], board_type=c["board_type"], board_slug=c["board_slug"]
        )
        for c in raw.get("companies", [])
    ]


def load_career_pages(path: Path = COMPANIES_FILE) -> list[CareerPageConfig]:
    raw = _load_yaml(path)
    return [
        CareerPageConfig(name=c["name"], url=c["url"])
        for c in raw.get("career_pages", [])
    ]


def load_search_queries(path: Path = COMPANIES_FILE) -> list[str]:
    raw = _load_yaml(path)
    return list(raw.get("search_queries", []))


def get_gemini_api_key() -> str:
    key = os.environ.get("GEMINI_API_KEY")
    if not key:
        raise RuntimeError("GEMINI_API_KEY not set in environment")
    return key


def get_gemini_model_name() -> str:
    return os.environ.get("GEMINI_MODEL", "gemini-2.0-flash")


def get_google_search_config() -> tuple[str, str]:
    api_key = os.environ.get("GOOGLE_SEARCH_API_KEY")
    cx = os.environ.get("GOOGLE_SEARCH_CX")
    if not api_key or not cx:
        raise RuntimeError("GOOGLE_SEARCH_API_KEY / GOOGLE_SEARCH_CX not set")
    return api_key, cx
```

- [ ] **Step 8: Run test to verify it passes**

Run: `cd backend && venv/bin/pytest tests/discovery/test_config.py -v`
Expected: PASS (9 tests)

- [ ] **Step 9: Commit**

```bash
git add backend/requirements.txt backend/.env.example backend/discovery/__init__.py backend/discovery/config.py backend/discovery/companies.yaml backend/tests/discovery/__init__.py backend/tests/discovery/test_config.py
git commit -m "feat: add discovery package scaffolding and config loading"
```

---

### Task 2: Gemini client wrapper

**Files:**
- Create: `backend/discovery/gemini_client.py`
- Test: `backend/tests/discovery/test_gemini_client.py`

**Interfaces:**
- Consumes: `discovery.config.get_gemini_api_key()`, `discovery.config.get_gemini_model_name()` (Task 1)
- Produces: `discovery.gemini_client.GeminiError` (Exception), `discovery.gemini_client.GeminiClient` with `__init__(self, api_key: str | None = None, model_name: str | None = None, model=None)` and `generate_json(self, prompt: str, retries: int = 1) -> dict`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/discovery/test_gemini_client.py
import pytest
from discovery.gemini_client import GeminiClient, GeminiError


class FakeResponse:
    def __init__(self, text):
        self.text = text


class FakeModel:
    def __init__(self, responses):
        self._responses = list(responses)
        self.calls = 0

    def generate_content(self, prompt):
        self.calls += 1
        response = self._responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return FakeResponse(response)


def test_generate_json_parses_plain_json():
    model = FakeModel(['{"a": 1, "b": true}'])
    client = GeminiClient(model=model)
    assert client.generate_json("prompt") == {"a": 1, "b": True}


def test_generate_json_strips_markdown_fence():
    model = FakeModel(['```json\n{"a": 1}\n```'])
    client = GeminiClient(model=model)
    assert client.generate_json("prompt") == {"a": 1}


def test_generate_json_retries_then_succeeds():
    model = FakeModel([RuntimeError("boom"), '{"a": 1}'])
    client = GeminiClient(model=model)
    result = client.generate_json("prompt", retries=1)
    assert result == {"a": 1}
    assert model.calls == 2


def test_generate_json_raises_gemini_error_after_exhausting_retries():
    model = FakeModel([RuntimeError("boom"), RuntimeError("boom again")])
    client = GeminiClient(model=model)
    with pytest.raises(GeminiError):
        client.generate_json("prompt", retries=1)
    assert model.calls == 2


def test_generate_json_raises_gemini_error_on_invalid_json():
    model = FakeModel(["not json at all"])
    client = GeminiClient(model=model)
    with pytest.raises(GeminiError):
        client.generate_json("prompt", retries=0)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && venv/bin/pytest tests/discovery/test_gemini_client.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'discovery.gemini_client'`

- [ ] **Step 3: Write discovery/gemini_client.py**

```python
import json
import time

import google.generativeai as genai

from . import config


class GeminiError(Exception):
    pass


class GeminiClient:
    def __init__(self, api_key: str | None = None, model_name: str | None = None, model=None):
        if model is not None:
            self._model = model
            return
        genai.configure(api_key=api_key or config.get_gemini_api_key())
        self._model = genai.GenerativeModel(model_name or config.get_gemini_model_name())

    def generate_json(self, prompt: str, retries: int = 1) -> dict:
        last_error: Exception | None = None
        for attempt in range(retries + 1):
            try:
                response = self._model.generate_content(prompt)
                text = response.text.strip()
                if text.startswith("```"):
                    text = text.strip("`")
                    if text.lower().startswith("json"):
                        text = text[4:]
                return json.loads(text.strip())
            except json.JSONDecodeError as exc:
                last_error = exc
                break
            except Exception as exc:  # noqa: BLE001 - any Gemini SDK/network failure
                last_error = exc
                if attempt < retries:
                    time.sleep(2**attempt)
        raise GeminiError(f"Gemini call failed after {retries + 1} attempt(s): {last_error}")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && venv/bin/pytest tests/discovery/test_gemini_client.py -v`
Expected: PASS (5 tests)

- [ ] **Step 5: Commit**

```bash
git add backend/discovery/gemini_client.py backend/tests/discovery/test_gemini_client.py
git commit -m "feat: add Gemini client wrapper with JSON parsing and retry"
```

---

### Task 3: RawPosting model and Adapter protocol

**Files:**
- Create: `backend/discovery/adapters/__init__.py`
- Create: `backend/discovery/adapters/base.py`
- Test: `backend/tests/discovery/test_base.py`

**Interfaces:**
- Produces: `discovery.adapters.base.RawPosting` (dataclass: `company: str`, `role_title: str`, `source: str`, `source_url: str`, `location: str | None = None`, `raw_description: str | None = None`, `posted_date: date | None = None`), `discovery.adapters.base.Adapter` (Protocol with `fetch(self) -> list[RawPosting]`)

- [ ] **Step 1: Create adapters package init**

`backend/discovery/adapters/__init__.py` — empty file.

- [ ] **Step 2: Write the failing test**

```python
# backend/tests/discovery/test_base.py
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
```

- [ ] **Step 3: Run test to verify it fails**

Run: `cd backend && venv/bin/pytest tests/discovery/test_base.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'discovery.adapters'`

- [ ] **Step 4: Write discovery/adapters/base.py**

```python
from dataclasses import dataclass
from datetime import date
from typing import Optional, Protocol


@dataclass
class RawPosting:
    company: str
    role_title: str
    source: str
    source_url: str
    location: Optional[str] = None
    raw_description: Optional[str] = None
    posted_date: Optional[date] = None


class Adapter(Protocol):
    def fetch(self) -> list[RawPosting]:
        ...
```

- [ ] **Step 5: Run test to verify it passes**

Run: `cd backend && venv/bin/pytest tests/discovery/test_base.py -v`
Expected: PASS (2 tests)

- [ ] **Step 6: Commit**

```bash
git add backend/discovery/adapters/__init__.py backend/discovery/adapters/base.py backend/tests/discovery/test_base.py
git commit -m "feat: add RawPosting model and Adapter protocol"
```

---

### Task 4: GitHub list adapter

**Files:**
- Create: `backend/discovery/adapters/github_list.py`
- Create: `backend/tests/discovery/fixtures/simplifyjobs_listings_sample.json`
- Create: `backend/tests/discovery/fixtures/vanshb03_listings_sample.json`
- Test: `backend/tests/discovery/test_github_list_adapter.py`

**Interfaces:**
- Consumes: `discovery.adapters.base.RawPosting` (Task 3)
- Produces: `discovery.adapters.github_list.GitHubListAdapter` with `__init__(self, repo: str, source_name: str, category_filter: set[str] | None = None, client: httpx.Client | None = None)` and `fetch(self) -> list[RawPosting]`; module-level constants `discovery.adapters.github_list.SIMPLIFYJOBS_REPO = "SimplifyJobs/Summer2027-Internships"`, `discovery.adapters.github_list.VANSHB03_REPO = "vanshb03/Summer2027-Internships"`, `discovery.adapters.github_list.RELEVANT_CATEGORIES = {"Software Engineering", "Software", "Data Science, AI & Machine Learning", "AI/ML/Data"}`

**Background on the two feeds (verified by fetching the real data during design):**

Both `SimplifyJobs/Summer2027-Internships` and `vanshb03/Summer2027-Internships` expose a machine-readable feed at `https://raw.githubusercontent.com/{repo}/dev/.github/scripts/listings.json`. The two feeds have **different schemas**:

- SimplifyJobs' feed is list of objects with keys: `source`, `category` (e.g. `"AI/ML/Data"`, `"Software Engineering"`), `company_name`, `id`, `title`, `active` (bool), `terms` (list of strings like `"Summer 2027"`), `date_updated`/`date_posted` (unix timestamps), `url`, `locations` (list of strings), `company_url`, `is_visible`, `sponsorship`, `degrees` (list). It has a `category` field, so role-relevance filtering can happen right in the adapter.
- vanshb03's feed has a **different, smaller schema**: `date_updated`, `url`, `locations`, `sponsorship`, `active`, `company_name`, `title`, `season` (single string: `"Summer"`/`"Fall"`/`"Winter"`/`"Spring"`), `source`, `id`, `date_posted`, `company_url`, `is_visible`. **No `category` field** — this feed cannot be filtered to SWE/AI/ML roles at the adapter level; that filtering happens later in the shared classifier (Task 5), which also determines role relevance.

Neither feed includes a job description field — postings from this adapter will have `raw_description=None`. The shared classifier (Task 5) must handle that gracefully.

- [ ] **Step 1: Create the SimplifyJobs test fixture**

```json
[
  {
    "source": "Simplify",
    "category": "AI/ML/Data",
    "company_name": "Grant Thornton",
    "id": "45e6cd12-c55d-47f0-b650-b2c4b472ce45",
    "title": "Tax Technology Intern - Summer 2027",
    "active": true,
    "terms": ["Summer 2027"],
    "date_updated": 1770822643,
    "date_posted": 1770822643,
    "url": "https://ehzq.fa.us2.oraclecloud.com/hcmUI/CandidateExperience/en/sites/CX_1/job/114405",
    "locations": ["Bellevue, WA"],
    "company_url": "https://simplify.jobs/c/Grant-Thornton",
    "is_visible": true,
    "sponsorship": "Other",
    "degrees": ["Bachelor's"]
  },
  {
    "source": "Simplify",
    "category": "Quant",
    "company_name": "FHLBank Atlanta",
    "id": "b6fbdfb9-cebf-429b-a7f2-e5c1e31611ed",
    "title": "Capital Markets Intern",
    "active": true,
    "terms": ["Summer 2027"],
    "date_updated": 1766516522,
    "date_posted": 1766516522,
    "url": "https://fhlbatl.wd1.myworkdayjobs.com/fhlbatl/job/Atlanta-Georgia/Capital-Markets-Intern_JR275",
    "locations": ["Atlanta, GA"],
    "company_url": "https://simplify.jobs/c/FHLBank-Atlanta",
    "is_visible": true,
    "sponsorship": "Other",
    "degrees": []
  },
  {
    "source": "Simplify",
    "category": "Software Engineering",
    "company_name": "Old Corp",
    "id": "aaaaaaaa-0000-0000-0000-000000000000",
    "title": "Backend Intern - Summer 2026",
    "active": false,
    "terms": ["Summer 2026"],
    "date_updated": 1700000000,
    "date_posted": 1700000000,
    "url": "https://oldcorp.example.com/jobs/backend",
    "locations": ["Austin, TX"],
    "company_url": "https://simplify.jobs/c/Old-Corp",
    "is_visible": true,
    "sponsorship": "Other",
    "degrees": []
  }
]
```

- [ ] **Step 2: Create the vanshb03 test fixture**

```json
[
  {
    "date_updated": 1776617698,
    "url": "https://careers.point72.com/CSJobDetail?jobName=summer-2027-quantitative-developer-internship&jobCode=CSS-0012293",
    "locations": ["New York, NY"],
    "sponsorship": "Other",
    "active": true,
    "company_name": "Point72",
    "title": "Quantitative Developer Intern",
    "source": "vanshb03",
    "id": "3dcc8f0b-f7f0-49db-800f-487fa5be8b4f",
    "date_posted": 1776617698,
    "company_url": "",
    "is_visible": true,
    "season": "Summer"
  },
  {
    "date_updated": 1776617702,
    "url": "https://careers.point72.com/CSJobDetail?jobName=summer-2027-quantitative-researcher-internship&jobCode=CSS-0012295",
    "locations": ["New York, NY"],
    "sponsorship": "Other",
    "active": true,
    "company_name": "Point72",
    "title": "Quantitative Researcher Intern",
    "source": "vanshb03",
    "id": "27cdff11-8ec9-4c5c-9919-a4c6c5585824",
    "date_posted": 1776617702,
    "company_url": "",
    "is_visible": true,
    "season": "Summer"
  },
  {
    "date_updated": 1700000000,
    "url": "https://oldcorp.example.com/jobs/winter-intern",
    "locations": ["Chicago, IL"],
    "sponsorship": "Other",
    "active": false,
    "company_name": "Old Corp",
    "title": "Winter Intern",
    "source": "vanshb03",
    "id": "bbbbbbbb-0000-0000-0000-000000000000",
    "date_posted": 1700000000,
    "company_url": "",
    "is_visible": true,
    "season": "Winter"
  }
]
```

- [ ] **Step 3: Write the failing test**

```python
# backend/tests/discovery/test_github_list_adapter.py
import json
from pathlib import Path

import httpx

from discovery.adapters.github_list import (
    GitHubListAdapter,
    SIMPLIFYJOBS_REPO,
    VANSHB03_REPO,
    RELEVANT_CATEGORIES,
)

FIXTURES = Path(__file__).parent / "fixtures"


def _client_returning(fixture_name: str) -> httpx.Client:
    payload = json.loads((FIXTURES / fixture_name).read_text())

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=payload)

    return httpx.Client(transport=httpx.MockTransport(handler))


def test_simplifyjobs_adapter_filters_by_category_and_active():
    client = _client_returning("simplifyjobs_listings_sample.json")
    adapter = GitHubListAdapter(
        repo=SIMPLIFYJOBS_REPO,
        source_name="simplifyjobs_github",
        category_filter=RELEVANT_CATEGORIES,
        client=client,
    )
    postings = adapter.fetch()

    assert len(postings) == 1
    posting = postings[0]
    assert posting.company == "Grant Thornton"
    assert posting.role_title == "Tax Technology Intern - Summer 2027"
    assert posting.source == "simplifyjobs_github"
    assert posting.source_url == (
        "https://ehzq.fa.us2.oraclecloud.com/hcmUI/CandidateExperience/en/sites/CX_1/job/114405"
    )
    assert posting.location == "Bellevue, WA"
    assert posting.raw_description is None


def test_simplifyjobs_adapter_excludes_wrong_category_and_inactive():
    client = _client_returning("simplifyjobs_listings_sample.json")
    adapter = GitHubListAdapter(
        repo=SIMPLIFYJOBS_REPO,
        source_name="simplifyjobs_github",
        category_filter=RELEVANT_CATEGORIES,
        client=client,
    )
    postings = adapter.fetch()
    companies = {p.company for p in postings}
    assert "FHLBank Atlanta" not in companies  # wrong category (Quant)
    assert "Old Corp" not in companies  # inactive


def test_vanshb03_adapter_has_no_category_filter():
    client = _client_returning("vanshb03_listings_sample.json")
    adapter = GitHubListAdapter(
        repo=VANSHB03_REPO,
        source_name="vanshb03_github",
        category_filter=None,
        client=client,
    )
    postings = adapter.fetch()

    assert len(postings) == 2
    companies = {p.company for p in postings}
    assert companies == {"Point72"}
    for posting in postings:
        assert posting.source == "vanshb03_github"


def test_vanshb03_adapter_excludes_inactive():
    client = _client_returning("vanshb03_listings_sample.json")
    adapter = GitHubListAdapter(
        repo=VANSHB03_REPO, source_name="vanshb03_github", category_filter=None, client=client
    )
    postings = adapter.fetch()
    urls = {p.source_url for p in postings}
    assert "https://oldcorp.example.com/jobs/winter-intern" not in urls
```

- [ ] **Step 4: Run test to verify it fails**

Run: `cd backend && venv/bin/pytest tests/discovery/test_github_list_adapter.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'discovery.adapters.github_list'`

- [ ] **Step 5: Write discovery/adapters/github_list.py**

```python
import json

import httpx

from .base import RawPosting

SIMPLIFYJOBS_REPO = "SimplifyJobs/Summer2027-Internships"
VANSHB03_REPO = "vanshb03/Summer2027-Internships"
RELEVANT_CATEGORIES = {
    "Software Engineering",
    "Software",
    "Data Science, AI & Machine Learning",
    "AI/ML/Data",
}


class GitHubListAdapter:
    def __init__(
        self,
        repo: str,
        source_name: str,
        category_filter: set[str] | None = None,
        client: httpx.Client | None = None,
    ):
        self.repo = repo
        self.source_name = source_name
        self.category_filter = category_filter
        self.listings_url = (
            f"https://raw.githubusercontent.com/{repo}/dev/.github/scripts/listings.json"
        )
        self._client = client or httpx.Client(timeout=30)

    def fetch(self) -> list[RawPosting]:
        response = self._client.get(self.listings_url)
        response.raise_for_status()
        entries = json.loads(response.text)

        postings = []
        for entry in entries:
            if not entry.get("active"):
                continue
            if self.category_filter is not None and entry.get("category") not in self.category_filter:
                continue
            locations = entry.get("locations") or []
            postings.append(
                RawPosting(
                    company=entry["company_name"],
                    role_title=entry["title"],
                    source=self.source_name,
                    source_url=entry["url"],
                    location=", ".join(locations) if locations else None,
                    raw_description=None,
                )
            )
        return postings
```

- [ ] **Step 6: Run test to verify it passes**

Run: `cd backend && venv/bin/pytest tests/discovery/test_github_list_adapter.py -v`
Expected: PASS (4 tests)

- [ ] **Step 7: Commit**

```bash
git add backend/discovery/adapters/github_list.py backend/tests/discovery/fixtures/simplifyjobs_listings_sample.json backend/tests/discovery/fixtures/vanshb03_listings_sample.json backend/tests/discovery/test_github_list_adapter.py
git commit -m "feat: add GitHub curated-list adapter for SimplifyJobs and vanshb03 feeds"
```

---

### Task 5: Classifier

**Files:**
- Create: `backend/discovery/classifier.py`
- Test: `backend/tests/discovery/test_classifier.py`

**Interfaces:**
- Consumes: `discovery.adapters.base.RawPosting` (Task 3), `discovery.gemini_client.GeminiClient`, `discovery.gemini_client.GeminiError` (Task 2)
- Produces: `discovery.classifier.ClassificationResult` (dataclass: `passed: bool`, `eligibility: str`, `paid: bool`), `discovery.classifier.classify_posting(client: GeminiClient, posting: RawPosting) -> ClassificationResult | None` (returns `None` if the Gemini call fails after retries — caller must treat that as "skip this posting for now")

**Design note:** postings from the GitHub list adapters have no description text (see Task 4) — the classifier must work from `company`, `role_title`, and `location` alone in that case, and the prompt instructs the model to default `eligibility` to `"all_levels"` when there's no explicit signal excluding sophomores/juniors (most internships don't state an exclusion at all; the common exclusionary cases — "must be a rising senior", "PhD only", "new grad" — usually do appear in a title or the little text available). `is_paid` defaults to `true` unless something explicitly signals unpaid/volunteer, since the overwhelming majority of tech internships from real companies are paid.

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/discovery/test_classifier.py
from discovery.adapters.base import RawPosting
from discovery.classifier import classify_posting
from discovery.gemini_client import GeminiError


class FakeGeminiClient:
    def __init__(self, result):
        self.result = result
        self.last_prompt = None

    def generate_json(self, prompt, retries=1):
        self.last_prompt = prompt
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


def _posting(**overrides):
    defaults = dict(
        company="Acme",
        role_title="AI Engineering Intern",
        source="test",
        source_url="https://example.com/jobs/1",
        location="San Francisco, CA",
        raw_description="Join our AI team as a Summer 2027 intern open to sophomores and juniors.",
    )
    defaults.update(overrides)
    return RawPosting(**defaults)


def test_classify_posting_passes_when_all_criteria_met():
    client = FakeGeminiClient(
        {
            "still_open": True,
            "is_summer_2027": True,
            "is_paid": True,
            "is_us_based": True,
            "eligibility": "soph_junior",
            "role_category": "swe_ai_ml",
        }
    )
    result = classify_posting(client, _posting())
    assert result.passed is True
    assert result.eligibility == "soph_junior"
    assert result.paid is True


def test_classify_posting_fails_when_not_open():
    client = FakeGeminiClient(
        {
            "still_open": False,
            "is_summer_2027": True,
            "is_paid": True,
            "is_us_based": True,
            "eligibility": "soph_junior",
            "role_category": "swe_ai_ml",
        }
    )
    result = classify_posting(client, _posting())
    assert result.passed is False


def test_classify_posting_fails_when_senior_only():
    client = FakeGeminiClient(
        {
            "still_open": True,
            "is_summer_2027": True,
            "is_paid": True,
            "is_us_based": True,
            "eligibility": "senior_only",
            "role_category": "swe_ai_ml",
        }
    )
    result = classify_posting(client, _posting())
    assert result.passed is False
    assert result.eligibility == "senior_only"


def test_classify_posting_fails_when_wrong_role_category():
    client = FakeGeminiClient(
        {
            "still_open": True,
            "is_summer_2027": True,
            "is_paid": True,
            "is_us_based": True,
            "eligibility": "all_levels",
            "role_category": "other",
        }
    )
    result = classify_posting(client, _posting())
    assert result.passed is False


def test_classify_posting_returns_none_on_gemini_failure():
    client = FakeGeminiClient(GeminiError("boom"))
    result = classify_posting(client, _posting())
    assert result is None


def test_classify_posting_includes_posting_fields_in_prompt():
    client = FakeGeminiClient(
        {
            "still_open": True,
            "is_summer_2027": True,
            "is_paid": True,
            "is_us_based": True,
            "eligibility": "all_levels",
            "role_category": "swe_ai_ml",
        }
    )
    classify_posting(client, _posting(company="UniqueCo", role_title="Unique Role Title"))
    assert "UniqueCo" in client.last_prompt
    assert "Unique Role Title" in client.last_prompt
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && venv/bin/pytest tests/discovery/test_classifier.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'discovery.classifier'`

- [ ] **Step 3: Write discovery/classifier.py**

```python
from dataclasses import dataclass

from .adapters.base import RawPosting
from .gemini_client import GeminiClient, GeminiError

CLASSIFY_PROMPT_TEMPLATE = """You are screening a job posting for a college student's Summer 2027 internship search (AI engineering, ML engineering, or software engineering roles only).

Posting:
Company: {company}
Role title: {role_title}
Location: {location}
Description: {raw_description}

Some postings above have no description text available - judge from the title/company/location alone in that case.

Answer with ONLY a JSON object (no other text, no markdown fence) with exactly these keys:
{{
  "still_open": true or false (assume true unless something indicates the posting is closed/expired),
  "is_summer_2027": true or false (must be for a Summer 2027 internship specifically, not Summer 2026/2028 or a different term),
  "is_paid": true or false (default true unless explicitly unpaid/volunteer),
  "is_us_based": true or false (based on the location, or the description if location is missing),
  "eligibility": one of "soph_junior", "all_levels", "freshman_only", "senior_only", "other" (default "all_levels" when there is no explicit statement restricting eligibility by class year; only use "freshman_only" or "senior_only" when the posting explicitly restricts to that class year alone),
  "role_category": "swe_ai_ml" if this is a software engineering, AI engineering, or ML engineering role, otherwise "other" (e.g. quant, hardware, product, sales, finance, etc. are "other")
}}
"""


@dataclass
class ClassificationResult:
    passed: bool
    eligibility: str
    paid: bool


def classify_posting(client: GeminiClient, posting: RawPosting) -> ClassificationResult | None:
    prompt = CLASSIFY_PROMPT_TEMPLATE.format(
        company=posting.company,
        role_title=posting.role_title,
        location=posting.location or "unknown",
        raw_description=posting.raw_description or "(no description available)",
    )
    try:
        result = client.generate_json(prompt)
    except GeminiError:
        return None

    eligibility = result.get("eligibility", "other")
    passed = (
        result.get("still_open") is True
        and result.get("is_summer_2027") is True
        and result.get("is_paid") is True
        and result.get("is_us_based") is True
        and eligibility in ("soph_junior", "all_levels")
        and result.get("role_category") == "swe_ai_ml"
    )
    return ClassificationResult(
        passed=passed,
        eligibility=eligibility,
        paid=bool(result.get("is_paid", False)),
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && venv/bin/pytest tests/discovery/test_classifier.py -v`
Expected: PASS (6 tests)

- [ ] **Step 5: Commit**

```bash
git add backend/discovery/classifier.py backend/tests/discovery/test_classifier.py
git commit -m "feat: add Gemini-based posting classifier"
```

---

### Task 6: Job board adapter (Greenhouse + Lever)

**Files:**
- Create: `backend/discovery/adapters/job_board.py`
- Create: `backend/tests/discovery/fixtures/greenhouse_sample.json`
- Create: `backend/tests/discovery/fixtures/lever_sample.json`
- Test: `backend/tests/discovery/test_job_board_adapter.py`

**Interfaces:**
- Consumes: `discovery.adapters.base.RawPosting` (Task 3), `discovery.config.CompanyBoardConfig` (Task 1)
- Produces: `discovery.adapters.job_board.JobBoardAdapter` with `__init__(self, companies: list[CompanyBoardConfig], client: httpx.Client | None = None)` and `fetch(self) -> list[RawPosting]`

**Background on the two board APIs (verified by fetching real, live public boards during design):**

- **Greenhouse**: `GET https://boards-api.greenhouse.io/v1/boards/{board_slug}/jobs?content=true` returns `{"jobs": [...], "meta": {...}}`. Each job has: `id`, `title`, `company_name`, `absolute_url`, `location: {"name": "..."}`, `updated_at`, `content` (the job description, but **double HTML-escaped** — e.g. `"&lt;div&gt;..."` — needs `html.unescape()` and then HTML-tag stripping to get plain text; use BeautifulSoup: `BeautifulSoup(html.unescape(content), "html.parser").get_text(separator=" ", strip=True)`).
- **Lever**: `GET https://api.lever.co/v0/postings/{board_slug}?mode=json` returns a plain list of postings. Each has: `id`, `text` (the title), `hostedUrl`, `categories: {"location": "...", "commitment": "...", "department": "...", "team": "..."}`, `createdAt` (milliseconds since epoch), and — usefully — `descriptionPlain` (already plain text, no HTML stripping needed).

- [ ] **Step 1: Create the Greenhouse test fixture**

```json
{
  "jobs": [
    {
      "id": 8503792002,
      "title": "Software Engineering Intern - Summer 2027",
      "company_name": "GitLab",
      "absolute_url": "https://job-boards.greenhouse.io/gitlab/jobs/8503792002",
      "location": {"name": "Remote, United States"},
      "updated_at": "2026-08-10T16:52:46-04:00",
      "content": "&lt;div&gt;&lt;p&gt;Join GitLab as a Summer 2027 intern. Open to sophomores and juniors.&lt;/p&gt;&lt;/div&gt;"
    },
    {
      "id": 9999999999,
      "title": "Account Executive",
      "company_name": "GitLab",
      "absolute_url": "https://job-boards.greenhouse.io/gitlab/jobs/9999999999",
      "location": {"name": "Remote, Italy"},
      "updated_at": "2026-08-10T16:52:46-04:00",
      "content": "&lt;div&gt;&lt;p&gt;Sales role, not an internship.&lt;/p&gt;&lt;/div&gt;"
    }
  ],
  "meta": {"total": 2}
}
```

- [ ] **Step 2: Create the Lever test fixture**

```json
[
  {
    "id": "f4746da4-8eb8-43e2-b7ce-bf3c7cf9640d",
    "text": "Machine Learning Intern - Summer 2027",
    "hostedUrl": "https://jobs.lever.co/zoox/f4746da4-8eb8-43e2-b7ce-bf3c7cf9640d",
    "categories": {
      "commitment": "Intern",
      "department": "Machine Learning",
      "location": "Foster City, CA",
      "team": "Perception"
    },
    "createdAt": 1777936261125,
    "descriptionPlain": "Join Zoox as a Summer 2027 machine learning intern. Open to sophomores and juniors."
  },
  {
    "id": "aaaa-bbbb",
    "text": "Senior Staff Engineer",
    "hostedUrl": "https://jobs.lever.co/zoox/aaaa-bbbb",
    "categories": {
      "commitment": "Full-time",
      "department": "Software",
      "location": "Foster City, CA",
      "team": "Platform"
    },
    "createdAt": 1777936261125,
    "descriptionPlain": "Senior full-time role, not an internship."
  }
]
```

- [ ] **Step 3: Write the failing test**

```python
# backend/tests/discovery/test_job_board_adapter.py
import json
from pathlib import Path

import httpx
import pytest

from discovery.adapters.job_board import JobBoardAdapter
from discovery.config import CompanyBoardConfig

FIXTURES = Path(__file__).parent / "fixtures"


def _client_with_fixtures():
    greenhouse_payload = json.loads((FIXTURES / "greenhouse_sample.json").read_text())
    lever_payload = json.loads((FIXTURES / "lever_sample.json").read_text())

    def handler(request: httpx.Request) -> httpx.Response:
        if "boards-api.greenhouse.io" in str(request.url):
            return httpx.Response(200, json=greenhouse_payload)
        if "api.lever.co" in str(request.url):
            return httpx.Response(200, json=lever_payload)
        return httpx.Response(404)

    return httpx.Client(transport=httpx.MockTransport(handler))


def test_fetches_and_normalizes_greenhouse_and_lever():
    companies = [
        CompanyBoardConfig(name="GitLab", board_type="greenhouse", board_slug="gitlab"),
        CompanyBoardConfig(name="Zoox", board_type="lever", board_slug="zoox"),
    ]
    adapter = JobBoardAdapter(companies=companies, client=_client_with_fixtures())
    postings = adapter.fetch()

    assert len(postings) == 4  # 2 jobs per board, filtering happens later in the classifier

    gitlab_intern = next(p for p in postings if p.source_url.endswith("8503792002"))
    assert gitlab_intern.company == "GitLab"
    assert gitlab_intern.role_title == "Software Engineering Intern - Summer 2027"
    assert gitlab_intern.source == "greenhouse"
    assert gitlab_intern.location == "Remote, United States"
    assert "Summer 2027 intern" in gitlab_intern.raw_description
    assert "&lt;" not in gitlab_intern.raw_description  # HTML unescaped and tags stripped

    zoox_intern = next(p for p in postings if "f4746da4" in p.source_url)
    assert zoox_intern.company == "Zoox"
    assert zoox_intern.role_title == "Machine Learning Intern - Summer 2027"
    assert zoox_intern.source == "lever"
    assert zoox_intern.location == "Foster City, CA"
    assert zoox_intern.raw_description == (
        "Join Zoox as a Summer 2027 machine learning intern. Open to sophomores and juniors."
    )


def test_unknown_board_type_raises_value_error():
    companies = [CompanyBoardConfig(name="Bad Co", board_type="workday", board_slug="badco")]
    adapter = JobBoardAdapter(companies=companies, client=_client_with_fixtures())
    with pytest.raises(ValueError):
        adapter.fetch()


def test_one_company_failing_does_not_stop_others():
    def handler(request: httpx.Request) -> httpx.Response:
        if "brokenco" in str(request.url):
            return httpx.Response(500)
        lever_payload = json.loads((FIXTURES / "lever_sample.json").read_text())
        return httpx.Response(200, json=lever_payload)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    companies = [
        CompanyBoardConfig(name="Broken Co", board_type="greenhouse", board_slug="brokenco"),
        CompanyBoardConfig(name="Zoox", board_type="lever", board_slug="zoox"),
    ]
    adapter = JobBoardAdapter(companies=companies, client=client)
    postings = adapter.fetch()
    assert len(postings) == 2  # only Zoox's postings, Broken Co's 500 was skipped
    assert all(p.company == "Zoox" for p in postings)
```

- [ ] **Step 4: Run test to verify it fails**

Run: `cd backend && venv/bin/pytest tests/discovery/test_job_board_adapter.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'discovery.adapters.job_board'`

- [ ] **Step 5: Write discovery/adapters/job_board.py**

```python
import html

import httpx
from bs4 import BeautifulSoup

from ..config import CompanyBoardConfig
from .base import RawPosting


def _clean_html(raw_html: str) -> str:
    unescaped = html.unescape(raw_html)
    return BeautifulSoup(unescaped, "html.parser").get_text(separator=" ", strip=True)


class JobBoardAdapter:
    def __init__(self, companies: list[CompanyBoardConfig], client: httpx.Client | None = None):
        self.companies = companies
        self._client = client or httpx.Client(timeout=30)

    def fetch(self) -> list[RawPosting]:
        postings: list[RawPosting] = []
        for company in self.companies:
            try:
                postings.extend(self._fetch_company(company))
            except httpx.HTTPStatusError:
                continue
        return postings

    def _fetch_company(self, company: CompanyBoardConfig) -> list[RawPosting]:
        if company.board_type == "greenhouse":
            return self._fetch_greenhouse(company)
        if company.board_type == "lever":
            return self._fetch_lever(company)
        raise ValueError(f"Unknown board_type: {company.board_type!r}")

    def _fetch_greenhouse(self, company: CompanyBoardConfig) -> list[RawPosting]:
        url = f"https://boards-api.greenhouse.io/v1/boards/{company.board_slug}/jobs?content=true"
        response = self._client.get(url)
        response.raise_for_status()
        data = response.json()
        postings = []
        for job in data.get("jobs", []):
            postings.append(
                RawPosting(
                    company=job.get("company_name", company.name),
                    role_title=job["title"],
                    source="greenhouse",
                    source_url=job["absolute_url"],
                    location=(job.get("location") or {}).get("name"),
                    raw_description=_clean_html(job.get("content", "")) or None,
                )
            )
        return postings

    def _fetch_lever(self, company: CompanyBoardConfig) -> list[RawPosting]:
        url = f"https://api.lever.co/v0/postings/{company.board_slug}?mode=json"
        response = self._client.get(url)
        response.raise_for_status()
        data = response.json()
        postings = []
        for job in data:
            categories = job.get("categories") or {}
            postings.append(
                RawPosting(
                    company=company.name,
                    role_title=job["text"],
                    source="lever",
                    source_url=job["hostedUrl"],
                    location=categories.get("location"),
                    raw_description=job.get("descriptionPlain") or None,
                )
            )
        return postings
```

- [ ] **Step 6: Run test to verify it passes**

Run: `cd backend && venv/bin/pytest tests/discovery/test_job_board_adapter.py -v`
Expected: PASS (3 tests)

- [ ] **Step 7: Commit**

```bash
git add backend/discovery/adapters/job_board.py backend/tests/discovery/fixtures/greenhouse_sample.json backend/tests/discovery/fixtures/lever_sample.json backend/tests/discovery/test_job_board_adapter.py
git commit -m "feat: add job board adapter for Greenhouse and Lever public APIs"
```

---

### Task 7: Web search adapter

**Files:**
- Create: `backend/discovery/adapters/web_search.py`
- Test: `backend/tests/discovery/test_web_search_adapter.py`

**Interfaces:**
- Consumes: `discovery.adapters.base.RawPosting` (Task 3), `discovery.gemini_client.GeminiClient`, `discovery.gemini_client.GeminiError` (Task 2)
- Produces: `discovery.adapters.web_search.WebSearchAdapter` with `__init__(self, queries: list[str], google_api_key: str, google_cx: str, gemini_client: GeminiClient, search_client: httpx.Client | None = None, page_client: httpx.Client | None = None, max_results_per_query: int = 5)` and `fetch(self) -> list[RawPosting]`

**Design:** for each query, call Google Custom Search JSON API (`GET https://www.googleapis.com/customsearch/v1?key={key}&cx={cx}&q={query}`), which returns `{"items": [{"title": ..., "link": ..., "snippet": ...}, ...]}`. For each result, fetch the page and ask Gemini to extract a single posting (or determine it isn't one). A page that isn't a real job posting (an aggregator page, a "jobs" landing page, a 404, etc.) is skipped — the extraction prompt asks Gemini to return `null` in that case, which the adapter must detect and skip rather than crash on.

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/discovery/test_web_search_adapter.py
import httpx

from discovery.adapters.web_search import WebSearchAdapter
from discovery.gemini_client import GeminiError


class FakeGeminiClient:
    def __init__(self, responses):
        self._responses = list(responses)
        self.prompts = []

    def generate_json(self, prompt, retries=1):
        self.prompts.append(prompt)
        result = self._responses.pop(0)
        if isinstance(result, Exception):
            raise result
        return result


def _search_client(items):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"items": items})

    return httpx.Client(transport=httpx.MockTransport(handler))


def _page_client(html_by_url: dict):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text=html_by_url.get(str(request.url), "<html></html>"))

    return httpx.Client(transport=httpx.MockTransport(handler))


def test_extracts_posting_from_search_result_page():
    search_client = _search_client(
        [{"title": "AI Intern - Acme", "link": "https://acme.example.com/jobs/1", "snippet": "..."}]
    )
    page_client = _page_client(
        {"https://acme.example.com/jobs/1": "<html><body>AI Engineering Intern at Acme, Summer 2027</body></html>"}
    )
    gemini = FakeGeminiClient(
        [
            {
                "is_job_posting": True,
                "company": "Acme",
                "role_title": "AI Engineering Intern",
                "location": "Remote",
                "description": "AI Engineering Intern at Acme, Summer 2027",
            }
        ]
    )
    adapter = WebSearchAdapter(
        queries=["AI engineering intern Summer 2027"],
        google_api_key="key",
        google_cx="cx",
        gemini_client=gemini,
        search_client=search_client,
        page_client=page_client,
    )
    postings = adapter.fetch()

    assert len(postings) == 1
    posting = postings[0]
    assert posting.company == "Acme"
    assert posting.role_title == "AI Engineering Intern"
    assert posting.source == "google_search"
    assert posting.source_url == "https://acme.example.com/jobs/1"
    assert posting.location == "Remote"


def test_skips_result_gemini_says_is_not_a_posting():
    search_client = _search_client(
        [{"title": "Careers at Acme", "link": "https://acme.example.com/careers", "snippet": "..."}]
    )
    page_client = _page_client({"https://acme.example.com/careers": "<html><body>See all our jobs</body></html>"})
    gemini = FakeGeminiClient([{"is_job_posting": False}])
    adapter = WebSearchAdapter(
        queries=["AI engineering intern Summer 2027"],
        google_api_key="key",
        google_cx="cx",
        gemini_client=gemini,
        search_client=search_client,
        page_client=page_client,
    )
    postings = adapter.fetch()
    assert postings == []


def test_skips_result_on_gemini_failure():
    search_client = _search_client(
        [{"title": "AI Intern - Acme", "link": "https://acme.example.com/jobs/1", "snippet": "..."}]
    )
    page_client = _page_client({"https://acme.example.com/jobs/1": "<html><body>content</body></html>"})
    gemini = FakeGeminiClient([GeminiError("boom")])
    adapter = WebSearchAdapter(
        queries=["AI engineering intern Summer 2027"],
        google_api_key="key",
        google_cx="cx",
        gemini_client=gemini,
        search_client=search_client,
        page_client=page_client,
    )
    postings = adapter.fetch()
    assert postings == []


def test_respects_max_results_per_query():
    items = [
        {"title": f"Result {i}", "link": f"https://example.com/{i}", "snippet": "..."} for i in range(10)
    ]
    search_client = _search_client(items)
    page_client = _page_client({})
    gemini = FakeGeminiClient([{"is_job_posting": False}] * 3)
    adapter = WebSearchAdapter(
        queries=["some query"],
        google_api_key="key",
        google_cx="cx",
        gemini_client=gemini,
        search_client=search_client,
        page_client=page_client,
        max_results_per_query=3,
    )
    adapter.fetch()
    assert len(gemini.prompts) == 3
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && venv/bin/pytest tests/discovery/test_web_search_adapter.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'discovery.adapters.web_search'`

- [ ] **Step 3: Write discovery/adapters/web_search.py**

```python
import httpx
from bs4 import BeautifulSoup

from ..gemini_client import GeminiClient, GeminiError
from .base import RawPosting

EXTRACTION_PROMPT_TEMPLATE = """You are looking at the text content of a web page found via search for internship postings.

Page URL: {url}
Page text (truncated): {page_text}

If this page is a single specific job/internship posting, respond with ONLY a JSON object (no markdown fence, no other text):
{{
  "is_job_posting": true,
  "company": "the hiring company's name",
  "role_title": "the job title",
  "location": "the job location, or null if not stated",
  "description": "a concise plain-text summary of the posting, 2-4 sentences"
}}

If this page is NOT a single specific job posting (e.g. it's a jobs listing/search page, a company homepage, an article, or an error page), respond with ONLY:
{{"is_job_posting": false}}
"""


class WebSearchAdapter:
    def __init__(
        self,
        queries: list[str],
        google_api_key: str,
        google_cx: str,
        gemini_client: GeminiClient,
        search_client: httpx.Client | None = None,
        page_client: httpx.Client | None = None,
        max_results_per_query: int = 5,
    ):
        self.queries = queries
        self.google_api_key = google_api_key
        self.google_cx = google_cx
        self.gemini_client = gemini_client
        self.max_results_per_query = max_results_per_query
        self._search_client = search_client or httpx.Client(timeout=30)
        self._page_client = page_client or httpx.Client(timeout=30)

    def fetch(self) -> list[RawPosting]:
        postings: list[RawPosting] = []
        for query in self.queries:
            for item in self._search(query)[: self.max_results_per_query]:
                posting = self._extract_posting(item["link"])
                if posting is not None:
                    postings.append(posting)
        return postings

    def _search(self, query: str) -> list[dict]:
        response = self._search_client.get(
            "https://www.googleapis.com/customsearch/v1",
            params={"key": self.google_api_key, "cx": self.google_cx, "q": query},
        )
        response.raise_for_status()
        return response.json().get("items", [])

    def _extract_posting(self, url: str) -> RawPosting | None:
        try:
            page_response = self._page_client.get(url)
            page_response.raise_for_status()
        except httpx.HTTPError:
            return None

        page_text = BeautifulSoup(page_response.text, "html.parser").get_text(
            separator=" ", strip=True
        )[:5000]
        prompt = EXTRACTION_PROMPT_TEMPLATE.format(url=url, page_text=page_text)

        try:
            result = self.gemini_client.generate_json(prompt)
        except GeminiError:
            return None

        if not result.get("is_job_posting"):
            return None

        return RawPosting(
            company=result["company"],
            role_title=result["role_title"],
            source="google_search",
            source_url=url,
            location=result.get("location"),
            raw_description=result.get("description"),
        )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && venv/bin/pytest tests/discovery/test_web_search_adapter.py -v`
Expected: PASS (4 tests)

- [ ] **Step 5: Commit**

```bash
git add backend/discovery/adapters/web_search.py backend/tests/discovery/test_web_search_adapter.py
git commit -m "feat: add web search adapter using Google Custom Search + Gemini extraction"
```

---

### Task 8: Career page adapter

**Files:**
- Create: `backend/discovery/adapters/career_page.py`
- Test: `backend/tests/discovery/test_career_page_adapter.py`

**Interfaces:**
- Consumes: `discovery.adapters.base.RawPosting` (Task 3), `discovery.config.CareerPageConfig` (Task 1), `discovery.gemini_client.GeminiClient`, `discovery.gemini_client.GeminiError` (Task 2)
- Produces: `discovery.adapters.career_page.CareerPageAdapter` with `__init__(self, pages: list[CareerPageConfig], gemini_client: GeminiClient, client: httpx.Client | None = None)` and `fetch(self) -> list[RawPosting]`

**Design:** unlike the web search adapter (one page = one posting), a career page listing is expected to contain **multiple** postings — the extraction prompt asks Gemini for a JSON array. The company name comes from config (already known), not extracted. **Known limitation** (documented, not solved here): if a career page is a JavaScript-rendered single-page app, a plain HTTP GET won't see the rendered job listings and the page text will be mostly empty — Gemini will correctly return an empty array in that case, which is safe (no crash, no bad data), just no postings from that company via this path. This is an accepted limitation per the spec's error-handling section (malformed/low-content source data is skipped, not treated as an error).

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/discovery/test_career_page_adapter.py
import httpx

from discovery.adapters.career_page import CareerPageAdapter
from discovery.config import CareerPageConfig
from discovery.gemini_client import GeminiError


class FakeGeminiClient:
    def __init__(self, responses):
        self._responses = list(responses)
        self.prompts = []

    def generate_json(self, prompt, retries=1):
        self.prompts.append(prompt)
        result = self._responses.pop(0)
        if isinstance(result, Exception):
            raise result
        return result


def _page_client(html_by_url: dict):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text=html_by_url.get(str(request.url), "<html></html>"))

    return httpx.Client(transport=httpx.MockTransport(handler))


def test_extracts_multiple_postings_from_one_page():
    page_client = _page_client(
        {"https://acme.example.com/careers": "<html><body>AI Intern, SWE Intern listings...</body></html>"}
    )
    gemini = FakeGeminiClient(
        [
            [
                {
                    "role_title": "AI Engineering Intern",
                    "location": "Remote",
                    "description": "Summer 2027 AI internship.",
                    "url": "https://acme.example.com/careers/ai-intern",
                },
                {
                    "role_title": "SWE Intern",
                    "location": "New York, NY",
                    "description": "Summer 2027 software engineering internship.",
                    "url": "https://acme.example.com/careers/swe-intern",
                },
            ]
        ]
    )
    adapter = CareerPageAdapter(
        pages=[CareerPageConfig(name="Acme", url="https://acme.example.com/careers")],
        gemini_client=gemini,
        client=page_client,
    )
    postings = adapter.fetch()

    assert len(postings) == 2
    assert all(p.company == "Acme" for p in postings)
    assert all(p.source == "career_page" for p in postings)
    titles = {p.role_title for p in postings}
    assert titles == {"AI Engineering Intern", "SWE Intern"}


def test_empty_extraction_returns_no_postings():
    page_client = _page_client({"https://emptyco.example.com/careers": "<html></html>"})
    gemini = FakeGeminiClient([[]])
    adapter = CareerPageAdapter(
        pages=[CareerPageConfig(name="EmptyCo", url="https://emptyco.example.com/careers")],
        gemini_client=gemini,
        client=page_client,
    )
    postings = adapter.fetch()
    assert postings == []


def test_gemini_failure_skips_that_page_but_not_others():
    page_client = _page_client(
        {
            "https://brokenco.example.com/careers": "<html>broken</html>",
            "https://goodco.example.com/careers": "<html>good</html>",
        }
    )
    gemini = FakeGeminiClient(
        [
            GeminiError("boom"),
            [
                {
                    "role_title": "SWE Intern",
                    "location": "Remote",
                    "description": "desc",
                    "url": "https://goodco.example.com/careers/swe",
                }
            ],
        ]
    )
    adapter = CareerPageAdapter(
        pages=[
            CareerPageConfig(name="Broken Co", url="https://brokenco.example.com/careers"),
            CareerPageConfig(name="Good Co", url="https://goodco.example.com/careers"),
        ],
        gemini_client=gemini,
        client=page_client,
    )
    postings = adapter.fetch()
    assert len(postings) == 1
    assert postings[0].company == "Good Co"


def test_page_fetch_failure_skips_that_page():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    gemini = FakeGeminiClient([])
    adapter = CareerPageAdapter(
        pages=[CareerPageConfig(name="DownCo", url="https://downco.example.com/careers")],
        gemini_client=gemini,
        client=client,
    )
    postings = adapter.fetch()
    assert postings == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && venv/bin/pytest tests/discovery/test_career_page_adapter.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'discovery.adapters.career_page'`

- [ ] **Step 3: Write discovery/adapters/career_page.py**

```python
import httpx
from bs4 import BeautifulSoup

from ..config import CareerPageConfig
from ..gemini_client import GeminiClient, GeminiError
from .base import RawPosting

EXTRACTION_PROMPT_TEMPLATE = """You are looking at the text content of {company}'s careers page.

Page text (truncated): {page_text}

Find every internship posting on this page that looks like a Summer 2027 AI engineering, ML engineering, or software engineering internship. Respond with ONLY a JSON array (no markdown fence, no other text) of objects, one per posting found:
[
  {{
    "role_title": "the job title",
    "location": "the job location, or null if not stated",
    "description": "a concise plain-text summary of the posting, 2-4 sentences",
    "url": "the direct URL to this specific posting if visible in the page text, otherwise the careers page URL itself"
  }}
]

If you find no such postings on this page, respond with ONLY: []
"""


class CareerPageAdapter:
    def __init__(
        self,
        pages: list[CareerPageConfig],
        gemini_client: GeminiClient,
        client: httpx.Client | None = None,
    ):
        self.pages = pages
        self.gemini_client = gemini_client
        self._client = client or httpx.Client(timeout=30)

    def fetch(self) -> list[RawPosting]:
        postings: list[RawPosting] = []
        for page in self.pages:
            postings.extend(self._fetch_page(page))
        return postings

    def _fetch_page(self, page: CareerPageConfig) -> list[RawPosting]:
        try:
            response = self._client.get(page.url)
            response.raise_for_status()
        except httpx.HTTPError:
            return []

        page_text = BeautifulSoup(response.text, "html.parser").get_text(
            separator=" ", strip=True
        )[:8000]
        prompt = EXTRACTION_PROMPT_TEMPLATE.format(company=page.name, page_text=page_text)

        try:
            results = self.gemini_client.generate_json(prompt)
        except GeminiError:
            return []

        postings = []
        for entry in results:
            postings.append(
                RawPosting(
                    company=page.name,
                    role_title=entry["role_title"],
                    source="career_page",
                    source_url=entry.get("url") or page.url,
                    location=entry.get("location"),
                    raw_description=entry.get("description"),
                )
            )
        return postings
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && venv/bin/pytest tests/discovery/test_career_page_adapter.py -v`
Expected: PASS (4 tests)

- [ ] **Step 5: Commit**

```bash
git add backend/discovery/adapters/career_page.py backend/tests/discovery/test_career_page_adapter.py
git commit -m "feat: add career page adapter with Gemini-based multi-posting extraction"
```

---

### Task 9: Pipeline orchestration

**Files:**
- Create: `backend/discovery/pipeline.py`
- Test: `backend/tests/discovery/test_pipeline.py`

**Interfaces:**
- Consumes: `discovery.adapters.base.RawPosting`, `discovery.adapters.base.Adapter` (Task 3), `discovery.classifier.classify_posting`, `discovery.classifier.ClassificationResult` (Task 5), `app.crud.create_or_update_job`, `app.crud.list_jobs`, `app.schemas.JobCreate`, `app.models.Eligibility`, `app.database.SessionLocal` (from sub-project 1, already merged)
- Produces: `discovery.pipeline.RunSummary` (dataclass: `found: int`, `passed_filter: int`, `written: int`, `errors: list[str]`), `discovery.pipeline.run_discovery(adapters: list[Adapter], classifier_client, db_session_factory=SessionLocal, sleep_between_gemini_calls: float = 1.0) -> RunSummary`

**Design:** iterate adapters with per-adapter try/except (errors collected into `RunSummary.errors`, adapter's postings just omitted on failure). For each posting from every adapter: classify (skip — not counted as an error — if the classifier returns `None`, i.e. Gemini failed after retries), sleep briefly to respect rate limits, check the fuzzy cross-source dedup (normalized `company` + normalized `role_title` compared via `difflib.SequenceMatcher` against existing `new`/`tailored` jobs already in the DB, ratio > 0.85 counts as a duplicate and is skipped), then write via `create_or_update_job` if it passed classification and isn't a duplicate.

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/discovery/test_pipeline.py
from datetime import date

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app import crud, schemas
from app.database import Base
from app.models import Eligibility, JobStatus
from discovery.adapters.base import RawPosting
from discovery.classifier import ClassificationResult
from discovery.pipeline import run_discovery


@pytest.fixture()
def db_session_factory():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)
    return TestingSessionLocal


class FakeAdapter:
    def __init__(self, postings=None, error=None):
        self._postings = postings or []
        self._error = error

    def fetch(self):
        if self._error:
            raise self._error
        return self._postings


class FakeClassifierClient:
    """Stands in for the Gemini client passed to classify_posting."""

    def __init__(self, results_by_role_title: dict):
        self.results_by_role_title = results_by_role_title

    def generate_json(self, prompt, retries=1):
        for role_title, result in self.results_by_role_title.items():
            if role_title in prompt:
                if isinstance(result, Exception):
                    raise result
                return result
        raise AssertionError(f"No fake classifier result configured for prompt: {prompt[:200]}")


def _posting(**overrides):
    defaults = dict(
        company="Acme",
        role_title="AI Engineering Intern",
        source="test_source",
        source_url="https://example.com/jobs/1",
        location="Remote",
        raw_description="Summer 2027 AI internship open to sophomores and juniors.",
    )
    defaults.update(overrides)
    return RawPosting(**defaults)


def _passing_result():
    return {
        "still_open": True,
        "is_summer_2027": True,
        "is_paid": True,
        "is_us_based": True,
        "eligibility": "soph_junior",
        "role_category": "swe_ai_ml",
    }


def test_writes_postings_that_pass_classification(db_session_factory):
    adapter = FakeAdapter(postings=[_posting()])
    client = FakeClassifierClient({"AI Engineering Intern": _passing_result()})

    summary = run_discovery(
        adapters=[adapter], classifier_client=client, db_session_factory=db_session_factory,
        sleep_between_gemini_calls=0,
    )

    assert summary.found == 1
    assert summary.passed_filter == 1
    assert summary.written == 1

    db = db_session_factory()
    jobs = crud.list_jobs(db)
    assert len(jobs) == 1
    assert jobs[0].company == "Acme"
    assert jobs[0].status == JobStatus.new
    assert jobs[0].eligibility == Eligibility.soph_junior


def test_skips_postings_that_fail_classification(db_session_factory):
    adapter = FakeAdapter(postings=[_posting()])
    failing_result = {**_passing_result(), "is_paid": False}
    client = FakeClassifierClient({"AI Engineering Intern": failing_result})

    summary = run_discovery(
        adapters=[adapter], classifier_client=client, db_session_factory=db_session_factory,
        sleep_between_gemini_calls=0,
    )

    assert summary.found == 1
    assert summary.passed_filter == 0
    assert summary.written == 0

    db = db_session_factory()
    assert crud.list_jobs(db) == []


def test_one_adapter_failing_does_not_stop_others(db_session_factory):
    broken_adapter = FakeAdapter(error=RuntimeError("source down"))
    working_adapter = FakeAdapter(postings=[_posting()])
    client = FakeClassifierClient({"AI Engineering Intern": _passing_result()})

    summary = run_discovery(
        adapters=[broken_adapter, working_adapter],
        classifier_client=client,
        db_session_factory=db_session_factory,
        sleep_between_gemini_calls=0,
    )

    assert summary.written == 1
    assert len(summary.errors) == 1
    assert "source down" in summary.errors[0]


def test_fuzzy_duplicate_from_different_source_is_skipped(db_session_factory):
    db = db_session_factory()
    crud.create_or_update_job(
        db,
        schemas.JobCreate(
            company="Acme",
            role_title="AI Engineering Intern",
            source="simplifyjobs_github",
            source_url="https://github-list.example.com/acme-ai-intern",
            discovered_date=date.today(),
            eligibility=Eligibility.soph_junior,
        ),
    )

    adapter = FakeAdapter(
        postings=[
            _posting(
                company="Acme",
                role_title="AI Engineering Intern",  # same company+role, different source_url
                source="greenhouse",
                source_url="https://boards.greenhouse.io/acme/jobs/1",
            )
        ]
    )
    client = FakeClassifierClient({"AI Engineering Intern": _passing_result()})

    summary = run_discovery(
        adapters=[adapter], classifier_client=client, db_session_factory=db_session_factory,
        sleep_between_gemini_calls=0,
    )

    assert summary.passed_filter == 1
    assert summary.written == 0  # duplicate, not written again

    jobs = crud.list_jobs(db_session_factory())
    assert len(jobs) == 1  # still just the original


def test_gemini_classification_failure_is_skipped_not_counted_as_error(db_session_factory):
    from discovery.gemini_client import GeminiError

    adapter = FakeAdapter(postings=[_posting()])
    client = FakeClassifierClient({"AI Engineering Intern": GeminiError("boom")})

    summary = run_discovery(
        adapters=[adapter], classifier_client=client, db_session_factory=db_session_factory,
        sleep_between_gemini_calls=0,
    )

    assert summary.found == 1
    assert summary.passed_filter == 0
    assert summary.written == 0
    assert summary.errors == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && venv/bin/pytest tests/discovery/test_pipeline.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'discovery.pipeline'`

- [ ] **Step 3: Write discovery/pipeline.py**

```python
import time
from dataclasses import dataclass, field
from datetime import date
from difflib import SequenceMatcher

from app import crud, schemas
from app.database import SessionLocal
from app.models import Eligibility, JobStatus

from .adapters.base import Adapter, RawPosting
from .classifier import classify_posting


@dataclass
class RunSummary:
    found: int = 0
    passed_filter: int = 0
    written: int = 0
    errors: list[str] = field(default_factory=list)


def _normalize(text: str) -> str:
    return " ".join(text.lower().split())


def _is_fuzzy_duplicate(posting: RawPosting, existing_jobs) -> bool:
    norm_company = _normalize(posting.company)
    norm_role = _normalize(posting.role_title)
    for job in existing_jobs:
        if job.status not in (JobStatus.new, JobStatus.tailored):
            continue
        company_ratio = SequenceMatcher(None, norm_company, _normalize(job.company)).ratio()
        role_ratio = SequenceMatcher(None, norm_role, _normalize(job.role_title)).ratio()
        if company_ratio > 0.85 and role_ratio > 0.85:
            return True
    return False


def run_discovery(
    adapters: list[Adapter],
    classifier_client,
    db_session_factory=SessionLocal,
    sleep_between_gemini_calls: float = 1.0,
) -> RunSummary:
    summary = RunSummary()
    all_postings: list[RawPosting] = []

    for adapter in adapters:
        try:
            all_postings.extend(adapter.fetch())
        except Exception as exc:  # noqa: BLE001 - one adapter's failure must not stop the run
            summary.errors.append(f"{adapter.__class__.__name__}: {exc}")

    summary.found = len(all_postings)

    db = db_session_factory()
    try:
        existing_jobs = crud.list_jobs(db)

        for posting in all_postings:
            result = classify_posting(classifier_client, posting)
            if sleep_between_gemini_calls:
                time.sleep(sleep_between_gemini_calls)

            if result is None or not result.passed:
                continue
            summary.passed_filter += 1

            if _is_fuzzy_duplicate(posting, existing_jobs):
                continue

            eligibility = Eligibility(result.eligibility)
            job = crud.create_or_update_job(
                db,
                schemas.JobCreate(
                    company=posting.company,
                    role_title=posting.role_title,
                    source=posting.source,
                    source_url=posting.source_url,
                    location=posting.location,
                    paid=result.paid,
                    eligibility=eligibility,
                    posted_date=posting.posted_date,
                    discovered_date=date.today(),
                    raw_job_description=posting.raw_description,
                ),
            )
            existing_jobs.append(job)
            summary.written += 1
    finally:
        db.close()

    return summary
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && venv/bin/pytest tests/discovery/test_pipeline.py -v`
Expected: PASS (5 tests)

- [ ] **Step 5: Commit**

```bash
git add backend/discovery/pipeline.py backend/tests/discovery/test_pipeline.py
git commit -m "feat: add discovery pipeline orchestration with dedup and error isolation"
```

---

### Task 10: Entry point, launchd schedule, and README

**Files:**
- Create: `backend/discover.py`
- Create: `backend/discovery/com.applicationbot.discovery.plist.template`
- Modify: `README.md`

**Interfaces:**
- Consumes: `discovery.config.load_company_boards`, `discovery.config.load_career_pages`, `discovery.config.load_search_queries`, `discovery.config.get_google_search_config` (Task 1), `discovery.gemini_client.GeminiClient` (Task 2), `discovery.adapters.github_list.GitHubListAdapter`, `discovery.adapters.github_list.SIMPLIFYJOBS_REPO`, `discovery.adapters.github_list.VANSHB03_REPO`, `discovery.adapters.github_list.RELEVANT_CATEGORIES` (Task 4), `discovery.adapters.job_board.JobBoardAdapter` (Task 6), `discovery.adapters.web_search.WebSearchAdapter` (Task 7), `discovery.adapters.career_page.CareerPageAdapter` (Task 8), `discovery.pipeline.run_discovery` (Task 9)

- [ ] **Step 1: Write backend/discover.py**

```python
import logging
import sys

from discovery import config
from discovery.adapters.career_page import CareerPageAdapter
from discovery.adapters.github_list import (
    RELEVANT_CATEGORIES,
    SIMPLIFYJOBS_REPO,
    VANSHB03_REPO,
    GitHubListAdapter,
)
from discovery.adapters.job_board import JobBoardAdapter
from discovery.adapters.web_search import WebSearchAdapter
from discovery.gemini_client import GeminiClient
from discovery.pipeline import run_discovery

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("discover")


def build_adapters(gemini_client: GeminiClient):
    company_boards = config.load_company_boards()
    career_pages = config.load_career_pages()
    search_queries = config.load_search_queries()
    google_api_key, google_cx = config.get_google_search_config()

    return [
        GitHubListAdapter(
            repo=SIMPLIFYJOBS_REPO,
            source_name="simplifyjobs_github",
            category_filter=RELEVANT_CATEGORIES,
        ),
        GitHubListAdapter(
            repo=VANSHB03_REPO,
            source_name="vanshb03_github",
            category_filter=None,
        ),
        JobBoardAdapter(companies=company_boards),
        WebSearchAdapter(
            queries=search_queries,
            google_api_key=google_api_key,
            google_cx=google_cx,
            gemini_client=gemini_client,
        ),
        CareerPageAdapter(pages=career_pages, gemini_client=gemini_client),
    ]


def main() -> int:
    try:
        gemini_client = GeminiClient()
        adapters = build_adapters(gemini_client)
    except RuntimeError as exc:
        logger.error("Discovery run aborted: %s", exc)
        return 1

    summary = run_discovery(adapters=adapters, classifier_client=gemini_client)

    logger.info(
        "Discovery run complete: found=%d passed_filter=%d written=%d errors=%d",
        summary.found,
        summary.passed_filter,
        summary.written,
        len(summary.errors),
    )
    for error in summary.errors:
        logger.warning("Adapter error: %s", error)

    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 2: Write backend/discovery/com.applicationbot.discovery.plist.template**

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.applicationbot.discovery</string>
    <key>ProgramArguments</key>
    <array>
        <string>REPLACE_WITH_ABSOLUTE_PATH_TO/backend/venv/bin/python</string>
        <string>REPLACE_WITH_ABSOLUTE_PATH_TO/backend/discover.py</string>
    </array>
    <key>WorkingDirectory</key>
    <string>REPLACE_WITH_ABSOLUTE_PATH_TO/backend</string>
    <key>StartInterval</key>
    <integer>21600</integer>
    <key>StandardOutPath</key>
    <string>REPLACE_WITH_ABSOLUTE_PATH_TO/backend/discovery.log</string>
    <key>StandardErrorPath</key>
    <string>REPLACE_WITH_ABSOLUTE_PATH_TO/backend/discovery.log</string>
</dict>
</plist>
```

- [ ] **Step 3: Add a Job Discovery section to README.md**

Add this section to the end of the existing `README.md` (append, do not remove existing content):

```markdown
## Job Discovery

Job Discovery finds real internship postings from four sources (curated
GitHub lists, Greenhouse/Lever job-board APIs, Google web search, and
configured company career pages), filters them with Gemini, and writes
matching postings into the tracker as `new` jobs.

### One-time setup

1. Copy `.env.example` to `.env` in `backend/` and fill in:
   - `GEMINI_API_KEY` — from [Google AI Studio](https://aistudio.google.com/)
   - `GOOGLE_SEARCH_API_KEY` and `GOOGLE_SEARCH_CX` — from the
     [Google Programmable Search Engine](https://programmablesearchengine.google.com/)
     control panel (free tier: 100 queries/day)
2. Edit `backend/discovery/companies.yaml` to add/remove target companies
   and career pages.
3. Install the new dependencies if you haven't already:
   `cd backend && venv/bin/pip install -r requirements.txt`

### Running manually

```bash
cd backend
venv/bin/python discover.py
```

### Running on a schedule (macOS launchd)

1. Copy `backend/discovery/com.applicationbot.discovery.plist.template`
   to `~/Library/LaunchAgents/com.applicationbot.discovery.plist`,
   replacing every `REPLACE_WITH_ABSOLUTE_PATH_TO` with this repo's
   absolute path on your machine.
2. Load it: `launchctl load ~/Library/LaunchAgents/com.applicationbot.discovery.plist`
3. It will then run automatically every 6 hours (`StartInterval` is in
   seconds; edit the plist to change the interval). Logs go to
   `backend/discovery.log`.
4. To stop it: `launchctl unload ~/Library/LaunchAgents/com.applicationbot.discovery.plist`
```

- [ ] **Step 4: Manually verify the entry point wires together correctly**

Run: `cd backend && venv/bin/python -c "from discover import build_adapters; from discovery.gemini_client import GeminiClient; import os; os.environ.setdefault('GEMINI_API_KEY', 'test'); os.environ.setdefault('GOOGLE_SEARCH_API_KEY', 'test'); os.environ.setdefault('GOOGLE_SEARCH_CX', 'test'); adapters = build_adapters(GeminiClient(model=object())); print([type(a).__name__ for a in adapters])"`
Expected: prints a list of 5 adapter class names (`GitHubListAdapter`, `GitHubListAdapter`, `JobBoardAdapter`, `WebSearchAdapter`, `CareerPageAdapter`) with no exceptions — confirms all imports and config loading wire together without needing real API keys.

- [ ] **Step 5: Commit**

```bash
git add backend/discover.py backend/discovery/com.applicationbot.discovery.plist.template README.md
git commit -m "feat: add discovery entry point, launchd schedule template, and docs"
```

---

### Task 11: End-to-end manual verification

**Files:** none (verification only)

**Interfaces:** none (uses everything from Tasks 1-10)

- [ ] **Step 1: Run the full automated test suite**

Run: `cd backend && venv/bin/pytest -v`
Expected: all tests pass, including the existing sub-project 1 tests and all `tests/discovery/` tests added in this plan.

- [ ] **Step 2: Set up real credentials**

Copy `backend/.env.example` to `backend/.env` and fill in a real `GEMINI_API_KEY` (from Google AI Studio's free tier) and real `GOOGLE_SEARCH_API_KEY`/`GOOGLE_SEARCH_CX` (from Google Programmable Search Engine's free tier). If you don't want to set up Google Custom Search credentials right now, that's fine — proceed to Step 3, and the web search adapter will simply fail with a clear `RuntimeError` at startup (per `get_google_search_config`'s behavior) rather than a confusing crash; note this in your findings rather than blocking on it.

- [ ] **Step 3: Run one real discovery pass**

Run: `cd backend && venv/bin/python discover.py`
Expected: log output showing `found=`, `passed_filter=`, `written=` counts greater than zero for at least the GitHub list and job-board sources (these don't depend on the Google Search credentials). Note any adapter errors logged — a handful of individual company 404s from stale board slugs in `companies.yaml` is expected and fine (the per-adapter/per-company error isolation from Task 6/9 handles it); a total failure of an entire adapter is not expected and should be investigated.

- [ ] **Step 4: Inspect what got written**

Run: `cd backend && venv/bin/python -c "from app.database import SessionLocal; from app import crud; db = SessionLocal(); jobs = crud.list_jobs(db); print(len(jobs), 'jobs total'); [print(j.company, '-', j.role_title, '-', j.source, '-', j.eligibility) for j in jobs[:20]]"`
Expected: a list of real, plausible Summer 2027 AI/ML/SWE internship postings — spot-check a few against their `source_url` in a browser to confirm they're genuinely open, paid, US-based, and not senior/freshman-restricted. Report any obviously wrong classifications (this is the filter-quality check the spec's testing section calls for) — a small number of misclassifications from an LLM-based filter is expected and acceptable; a systematic failure (e.g. every posting is wrong) is not and should be investigated.

- [ ] **Step 5: Confirm the dashboard reflects the new jobs**

Start both servers as described in the main README (`uvicorn app.main:app --reload` and `npm run dev`) and open `http://localhost:5173`. Confirm the newly discovered jobs appear in the job list table with status `new`.
