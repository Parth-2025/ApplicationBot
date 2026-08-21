import enum
from sqlalchemy import (
    Column, Integer, String, Boolean, Date, Text, Enum, ForeignKey, UniqueConstraint
)
from sqlalchemy.orm import relationship
from .database import Base


class Eligibility(str, enum.Enum):
    soph_junior = "soph_junior"
    all_levels = "all_levels"
    freshman_only = "freshman_only"
    senior_only = "senior_only"
    other = "other"


class JobStatus(str, enum.Enum):
    new = "new"
    tailored = "tailored"
    applied = "applied"
    rejected = "rejected"
    ignored = "ignored"


class Job(Base):
    __tablename__ = "jobs"
    __table_args__ = (
        UniqueConstraint("company", "role_title", "source_url", name="uq_job_identity"),
    )

    id = Column(Integer, primary_key=True)
    company = Column(String, nullable=False)
    role_title = Column(String, nullable=False)
    source = Column(String, nullable=False)
    source_url = Column(String, nullable=False)
    location = Column(String, nullable=True)
    paid = Column(Boolean, nullable=False, default=True)
    eligibility = Column(Enum(Eligibility), nullable=False, default=Eligibility.other)
    still_open = Column(Boolean, nullable=False, default=True)
    us_based = Column(Boolean, nullable=False, default=True)
    posted_date = Column(Date, nullable=True)
    discovered_date = Column(Date, nullable=False)
    status = Column(Enum(JobStatus), nullable=False, default=JobStatus.new)
    raw_job_description = Column(Text, nullable=True)

    applications = relationship(
        "Application", back_populates="job", cascade="all, delete-orphan"
    )


class Application(Base):
    __tablename__ = "applications"

    id = Column(Integer, primary_key=True)
    job_id = Column(Integer, ForeignKey("jobs.id"), nullable=False)
    tailored_resume_path = Column(String, nullable=True)
    contact_email = Column(String, nullable=True)
    applied_date = Column(Date, nullable=True)
    application_number = Column(String, nullable=True)
    notes = Column(Text, nullable=True)

    job = relationship("Job", back_populates="applications")
