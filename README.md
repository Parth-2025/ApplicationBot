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
