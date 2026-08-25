# backend/tests/test_load_resume.py
from datetime import date

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app import crud
from app.models import MasterResume
import load_resume


@pytest.fixture()
def db_session_factory():
    engine = create_engine(
        "sqlite:///:memory:", connect_args={"check_same_thread": False}
    )
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)
    return TestingSessionLocal


def test_main_extracts_and_saves_master_resume(db_session_factory, monkeypatch):
    monkeypatch.setattr(
        load_resume, "extract_text_from_pdf", lambda path: "Fake resume text"
    )

    load_resume.main("/fake/path.pdf", db_session_factory=db_session_factory)

    db = db_session_factory()
    resume = crud.get_master_resume(db)
    assert resume is not None
    assert resume.content == "Fake resume text"
    assert resume.updated_date == date.today()


def test_main_overwrites_rather_than_duplicates(db_session_factory, monkeypatch):
    monkeypatch.setattr(
        load_resume, "extract_text_from_pdf", lambda path: "First version"
    )
    load_resume.main("/fake/path.pdf", db_session_factory=db_session_factory)

    monkeypatch.setattr(
        load_resume, "extract_text_from_pdf", lambda path: "Second version"
    )
    load_resume.main("/fake/path.pdf", db_session_factory=db_session_factory)

    db = db_session_factory()
    assert db.query(MasterResume).count() == 1
    assert crud.get_master_resume(db).content == "Second version"
