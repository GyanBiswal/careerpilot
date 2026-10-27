"""Plain-Python helpers for analysis: no LLM calls happen here."""
import hashlib
import json

from app.schemas.analysis import ResumeJDAnalysis

# Bump this whenever the prompt or schema changes so old cached results
# are reported as outdated.
PROMPT_VERSION = "v1"

# Keeps requests within the model's token limits and Groq's rate limits.
MAX_ANALYSIS_INPUT_CHARS = 15_000


def compute_input_hash(
    *,
    company_name: str,
    job_title: str,
    experience_category: str,
    resume_text: str,
    job_description_text: str,
) -> str:
    payload = json.dumps(
        [
            PROMPT_VERSION,
            company_name,
            job_title,
            experience_category,
            resume_text,
            job_description_text,
        ],
        ensure_ascii=False,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def compute_match_score(result: ResumeJDAnalysis) -> int | None:
    """Percent of required skills that have evidence in the resume.

    Returns None when the job description lists no required skills.
    """
    matched = sum(1 for s in result.matched_skills if s.importance == "required")
    missing = sum(1 for s in result.missing_skills if s.importance == "required")
    total = matched + missing
    if total == 0:
        return None
    return round(100 * matched / total)