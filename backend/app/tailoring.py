# backend/app/tailoring.py
from discovery.gemini_client import GeminiClient

from . import models

TAILOR_PROMPT_TEMPLATE = """You are helping a student tailor their resume for one specific internship posting.

Master resume (this is the student's real, current resume - a single page):
---
{master_resume}
---

Target posting:
Company: {company}
Role title: {role_title}
Description: {job_description}

Rewrite the master resume above so its wording is tailored to this posting - matching its language, emphasizing the most relevant experience, and aligning keywords where genuinely applicable.

Hard constraints, all of which must hold:
- Keep the exact same sections, in the exact same order, as the master resume.
- Keep the exact same number of bullet points under each role/project entry - do not add, remove, split, or merge bullets.
- Keep each rewritten bullet approximately the same length (word count) as the original it replaces.
- Do not add, remove, or reorder any role, project, or section.
- Do not invent experience, skills, projects, or qualifications that aren't in the master resume.
- The result must still fit on a single page when formatted the same way as the master resume - you are producing a drop-in replacement, not a longer or shorter document.

Output ONLY the tailored resume text - no commentary, no markdown code fences, no explanation of what you changed.
"""


def generate_tailored_resume(
    client: GeminiClient, master_resume_text: str, job: models.Job
) -> str:
    prompt = TAILOR_PROMPT_TEMPLATE.format(
        master_resume=master_resume_text,
        company=job.company,
        role_title=job.role_title,
        job_description=job.raw_job_description or "(no description available)",
    )
    return client.generate_text(prompt)
