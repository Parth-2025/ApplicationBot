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
