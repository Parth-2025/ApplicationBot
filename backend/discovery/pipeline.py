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
