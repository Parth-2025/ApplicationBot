from dataclasses import dataclass, field
from datetime import date
from difflib import SequenceMatcher

from app import crud, schemas
from app.database import SessionLocal
from app.models import Eligibility, JobStatus

from .adapters.base import Adapter, RawPosting
from .classifier import classify_postings_batch
from .gemini_client import GeminiQuotaExhaustedError


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


def _chunk(items: list, size: int):
    for i in range(0, len(items), size):
        yield items[i : i + size]


_INTERN_KEYWORDS = ("intern", "co-op", "coop")


def _looks_like_internship(role_title: str) -> bool:
    lowered = role_title.lower()
    return any(keyword in lowered for keyword in _INTERN_KEYWORDS)


def run_discovery(
    adapters: list[Adapter],
    classifier_client,
    db_session_factory=SessionLocal,
    classification_batch_size: int = 25,
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
        known_source_urls = {job.source_url for job in existing_jobs}

        # Two free (no-Gemini-call) pre-filters before classification, since
        # the daily request cap is the real bottleneck, not per-call cost:
        #   - skip postings whose exact source_url is already in the DB
        #     (a run every 6 hours mostly rediscovers what it already has)
        #   - skip postings whose title doesn't look like an internship/
        #     co-op at all (job-board adapters return a company's entire
        #     board, not just internships)
        # This maximizes how many *new, plausibly relevant* postings fit
        # in the day's quota instead of spending it on repeats and noise.
        candidates = [
            posting
            for posting in all_postings
            if posting.source_url not in known_source_urls
            and _looks_like_internship(posting.role_title)
        ]

        # Batching many postings into one Gemini call (instead of one call
        # per posting) is what makes classification feasible at all under
        # the free tier's daily request cap. GeminiClient itself paces
        # every call across its callers, so batches run sequentially here
        # rather than concurrently - concurrency wouldn't add throughput
        # under a shared rate limit, only complexity. Each batch's results
        # are written to the DB immediately (not held until the whole run
        # finishes) so a killed/crashed run, or one that hits the daily
        # quota partway through, keeps whatever it already found.
        for batch in _chunk(candidates, classification_batch_size):
            try:
                results = classify_postings_batch(classifier_client, batch)
            except GeminiQuotaExhaustedError as exc:
                summary.errors.append(f"Stopped early: {exc}")
                break

            for posting, result in zip(batch, results):
                if result is None or not result.passed:
                    continue
                summary.passed_filter += 1

                if _is_fuzzy_duplicate(posting, existing_jobs):
                    continue

                try:
                    eligibility = Eligibility(result.eligibility)
                except ValueError:
                    eligibility = Eligibility.other
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
                        still_open=result.still_open,
                        us_based=result.us_based,
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
