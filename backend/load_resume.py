# backend/load_resume.py
import sys
from pathlib import Path

import pypdf

from app import crud
from app.database import Base, SessionLocal, engine


def extract_text_from_pdf(pdf_path: Path) -> str:
    reader = pypdf.PdfReader(str(pdf_path))
    return "\n".join(page.extract_text() or "" for page in reader.pages)


def main(pdf_path: str, db_session_factory=SessionLocal) -> None:
    content = extract_text_from_pdf(Path(pdf_path))
    db = db_session_factory()
    try:
        crud.save_master_resume(db, content)
    finally:
        db.close()
    print(f"Loaded master resume from {pdf_path} ({len(content)} characters).")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: venv/bin/python load_resume.py <path-to-resume.pdf>")
        sys.exit(1)
    Base.metadata.create_all(bind=engine)
    main(sys.argv[1])
