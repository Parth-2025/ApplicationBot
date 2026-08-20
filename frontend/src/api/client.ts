// frontend/src/api/client.ts
export interface Job {
  id: number;
  company: string;
  role_title: string;
  source: string;
  source_url: string;
  location: string | null;
  paid: boolean;
  eligibility: string;
  posted_date: string | null;
  discovered_date: string;
  status: "new" | "tailored" | "applied" | "rejected" | "ignored";
  raw_job_description: string | null;
  applied_date?: string | null;
  application_number?: string | null;
  notes?: string | null;
}

const API_BASE = "http://localhost:8000";

async function extractErrorMessage(res: Response, fallback: string): Promise<string> {
  const body = await res.json().catch(() => null);
  return body?.detail ?? fallback;
}

export async function fetchJobs(): Promise<Job[]> {
  const res = await fetch(`${API_BASE}/jobs`);
  if (!res.ok) throw new Error(await extractErrorMessage(res, "Failed to fetch jobs"));
  return res.json();
}

export async function fetchJob(id: number): Promise<Job> {
  const res = await fetch(`${API_BASE}/jobs/${id}`);
  if (!res.ok) throw new Error(await extractErrorMessage(res, "Failed to fetch job"));
  return res.json();
}

export interface MarkAppliedPayload {
  status: "applied";
  applied_date: string;
  application_number?: string;
  notes?: string;
}

export async function markApplied(
  id: number,
  payload: MarkAppliedPayload
): Promise<Job> {
  const res = await fetch(`${API_BASE}/jobs/${id}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!res.ok)
    throw new Error(await extractErrorMessage(res, "Failed to mark job applied"));
  return res.json();
}

export async function updateJobStatus(id: number, status: string): Promise<Job> {
  const res = await fetch(`${API_BASE}/jobs/${id}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ status }),
  });
  if (!res.ok)
    throw new Error(await extractErrorMessage(res, "Failed to update job status"));
  return res.json();
}
