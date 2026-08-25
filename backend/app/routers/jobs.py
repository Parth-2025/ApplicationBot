from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from discovery.gemini_client import GeminiClient, GeminiError
from .. import crud, models, schemas
from ..database import get_db
from ..tailoring import generate_tailored_resume

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


_gemini_client: GeminiClient | None = None


def get_gemini_client() -> GeminiClient:
    global _gemini_client
    if _gemini_client is None:
        try:
            _gemini_client = GeminiClient()
        except RuntimeError:
            raise HTTPException(
                status_code=503,
                detail="GEMINI_API_KEY not set - see README",
            )
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
