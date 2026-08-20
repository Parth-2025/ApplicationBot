from datetime import date
from sqlalchemy.orm import Session
from . import models, schemas


class InvalidStatusTransition(Exception):
    pass


ALLOWED_TRANSITIONS = {
    models.JobStatus.new: {models.JobStatus.tailored, models.JobStatus.ignored, models.JobStatus.rejected},
    models.JobStatus.tailored: {models.JobStatus.ignored, models.JobStatus.rejected},
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
    if job.status != models.JobStatus.tailored:
        raise InvalidStatusTransition(
            f"Cannot transition job {job.id} from {job.status} to {models.JobStatus.applied}"
        )
    job.status = models.JobStatus.applied
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
