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
