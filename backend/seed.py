# backend/seed.py
from datetime import date
from app.database import SessionLocal, Base, engine
from app import crud, schemas
from app.models import JobStatus, Eligibility

Base.metadata.create_all(bind=engine)

db = SessionLocal()

job1 = crud.create_or_update_job(
    db,
    schemas.JobCreate(
        company="Example Corp",
        role_title="AI Engineering Intern",
        source="manual-seed",
        source_url="https://example.com/jobs/1",
        location="Remote",
        paid=True,
        eligibility=Eligibility.soph_junior,
        discovered_date=date.today(),
        raw_job_description="Build and evaluate LLM-powered features.",
    ),
)

job2 = crud.create_or_update_job(
    db,
    schemas.JobCreate(
        company="Sample Inc",
        role_title="SWE Intern",
        source="manual-seed",
        source_url="https://example.com/jobs/2",
        location="Maryland",
        paid=True,
        eligibility=Eligibility.soph_junior,
        discovered_date=date.today(),
        raw_job_description="Full-stack web development on core product.",
    ),
)
crud.update_job_status(db, job2, JobStatus.tailored)

db.close()
print("Seeded 2 sample jobs.")
