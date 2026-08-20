from datetime import date
from typing import Optional
from pydantic import BaseModel, ConfigDict
from .models import Eligibility, JobStatus


class JobBase(BaseModel):
    company: str
    role_title: str
    source: str
    source_url: str
    location: Optional[str] = None
    paid: bool = True
    eligibility: Eligibility = Eligibility.other
    posted_date: Optional[date] = None
    raw_job_description: Optional[str] = None


class JobCreate(JobBase):
    discovered_date: date


class JobUpdate(BaseModel):
    status: Optional[JobStatus] = None
    applied_date: Optional[date] = None
    application_number: Optional[str] = None
    notes: Optional[str] = None


class JobOut(JobBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    discovered_date: date
    status: JobStatus
    applied_date: Optional[date] = None
    application_number: Optional[str] = None
    notes: Optional[str] = None
    tailored_resume_path: Optional[str] = None
