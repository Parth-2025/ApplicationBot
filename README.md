# ApplicationBot

ApplicationBot is a local internship application tracker: it ingests job
postings, tracks their status through your application pipeline (new →
tailored → applied → rejected/ignored), and gives you a simple UI to review
and act on them.

## Prerequisites

- Python 3.11+
- Node.js (18+ recommended)

## Backend setup + run

From the repo root:

```bash
cd backend
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

The API server runs at `http://localhost:8000`.

## Frontend setup + run

From the repo root, in a separate terminal:

```bash
cd frontend
npm install
npm run dev
```

The frontend runs at `http://localhost:5173`.

## Loading sample data (optional)

With the backend venv active:

```bash
cd backend
source venv/bin/activate
python seed.py
```

This populates the local SQLite database with sample jobs so you have
something to look at in the UI right away.

## Running both together

Both servers must be running simultaneously for the app to work: the
backend on `:8000` and the frontend on `:5173`. The frontend talks to the
backend directly over `http://localhost:8000`.

## Job Discovery

Job Discovery finds real internship postings from four sources (curated
GitHub lists, Greenhouse/Lever job-board APIs, Google web search, and
configured company career pages), filters them with Gemini, and writes
matching postings into the tracker as `new` jobs.

### One-time setup

1. Copy `.env.example` to `.env` in `backend/` and fill in:
   - `GEMINI_API_KEY` — from [Google AI Studio](https://aistudio.google.com/)
   - `GOOGLE_SEARCH_API_KEY` and `GOOGLE_SEARCH_CX` — from the
     [Google Programmable Search Engine](https://programmablesearchengine.google.com/)
     control panel (free tier: 100 queries/day)
2. Edit `backend/discovery/companies.yaml` to add/remove target companies
   and career pages.
3. Install the new dependencies if you haven't already:
   `cd backend && venv/bin/pip install -r requirements.txt`

### Running manually

```bash
cd backend
venv/bin/python discover.py
```

### Running on a schedule (macOS launchd)

1. Copy `backend/discovery/com.applicationbot.discovery.plist.template`
   to `~/Library/LaunchAgents/com.applicationbot.discovery.plist`,
   replacing every `REPLACE_WITH_ABSOLUTE_PATH_TO` with this repo's
   absolute path on your machine.
2. Load it: `launchctl load ~/Library/LaunchAgents/com.applicationbot.discovery.plist`
3. It will then run automatically every 6 hours (`StartInterval` is in
   seconds; edit the plist to change the interval). Logs go to
   `backend/discovery.log`.
4. To stop it: `launchctl unload ~/Library/LaunchAgents/com.applicationbot.discovery.plist`

## Resume Tailoring

Resume Tailoring generates a draft of your resume tailored to a specific
job posting, using Gemini to rewrite your master resume around that
posting's requirements. You review the draft, edit it as needed, and save
it against the job.

### One-time setup

1. Install the new dependencies if you haven't already:
   `cd backend && venv/bin/pip install -r requirements.txt`
   (this adds `pypdf`, used to extract text from your resume PDF).
2. Load your master resume text into the tracker:
   ```bash
   cd backend
   venv/bin/python load_resume.py <path-to-your-resume.pdf>
   ```
   This is required before tailoring will work - without it,
   "Generate Tailored Resume" returns a 404 ("No master resume loaded").
   Re-running `load_resume.py` replaces the previously stored resume, so
   re-run it whenever you update your real resume.

### Using it

1. Open a job's detail page in the dashboard.
2. Click "Generate Tailored Resume" to have Gemini draft a tailored
   version based on your master resume and that job's posting.
3. Review and edit the draft as needed.
4. Click "Save" to store it against the job.

## Upgrading an existing database

The `applications` table's `tailored_resume_path` column was renamed to
`tailored_resume_text` (and changed to store resume text directly rather
than a file path) as part of adding Resume Tailoring. This repo has no
migration framework (no Alembic), and `Base.metadata.create_all` only
creates missing tables - it never alters existing ones - so if you have
an existing `backend/applicationbot.db` from before this change, the
`/jobs` endpoints will 500 with `sqlite3.OperationalError: no such
column: applications.tailored_resume_text` until you apply this one-time
fix:

```bash
cd backend
venv/bin/python -c "
import sqlite3
conn = sqlite3.connect('applicationbot.db')
conn.execute('ALTER TABLE applications ADD COLUMN tailored_resume_text TEXT')
conn.commit()
print('Migration applied.')
"
```

If you're starting from a fresh database (no pre-existing
`applicationbot.db`), no action is needed - `create_all` will create the
table with the correct column already.
