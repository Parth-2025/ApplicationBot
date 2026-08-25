from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from .. import crud, models, schemas
from ..database import get_db

router = APIRouter(prefix="/jobs", tags=["jobs"])


def _to_job_out(job: models.Job) -> schemas.JobOut:
    """Convert an ORM Job to JobOut, overlaying the latest Application's
    fields (applied_date, application_number, notes, tailored_resume_text)
    if one exists, since those fields live on a separate table."""
    job_out = schemas.JobOut.model_validate(job)
    if job.applications:
        latest = job.applications[-1]
        job_out.applied_date = latest.applied_date
        job_out.application_number = latest.application_number
        job_out.notes = latest.notes
        job_out.tailored_resume_text = latest.tailored_resume_text
    return job_out


@router.get("", response_model=list[schemas.JobOut])
def list_jobs(db: Session = Depends(get_db)):
    return [_to_job_out(job) for job in crud.list_jobs(db)]


@router.get("/{job_id}", response_model=schemas.JobOut)
def get_job(job_id: int, db: Session = Depends(get_db)):
    job = crud.get_job(db, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return _to_job_out(job)


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
            updated = crud.mark_applied(
                db,
                job,
                applied_date=job_update.applied_date,
                application_number=job_update.application_number,
                notes=job_update.notes,
            )
            return _to_job_out(updated)
        except crud.InvalidStatusTransition as exc:
            raise HTTPException(status_code=409, detail=str(exc))

    try:
        updated = crud.update_job_status(db, job, job_update.status)
        return _to_job_out(updated)
    except crud.InvalidStatusTransition as exc:
        raise HTTPException(status_code=409, detail=str(exc))


@router.get("/{job_id}/resume")
def get_resume(job_id: int, db: Session = Depends(get_db)):
    job = crud.get_job(db, job_id)
    if job is None or not job.applications:
        raise HTTPException(status_code=404, detail="No tailored resume for this job")
    resume_path = job.applications[-1].tailored_resume_text
    if not resume_path:
        raise HTTPException(status_code=404, detail="No tailored resume for this job")
    return FileResponse(resume_path, media_type="application/pdf")
