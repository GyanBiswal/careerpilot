import logging

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.ai.analysis_chain import analyze_resume_against_job
from app.ai.llm import AIServiceError
from app.api.deps import get_owned_application
from app.core.config import get_settings
from app.db.session import get_db
from app.models.analysis import ResumeAnalysis
from app.models.job_application import JobApplication
from app.models.job_description import JobDescription
from app.models.resume import Resume
from app.schemas.analysis import AnalysisRead, AnalysisRunResponse
from app.services.analysis_service import (
    MAX_ANALYSIS_INPUT_CHARS,
    compute_input_hash,
    compute_match_score,
)

logger = logging.getLogger("careerpilot.analysis")
settings = get_settings()

router = APIRouter(
    prefix="/applications/{application_id}/analysis", tags=["Analysis"]
)


def _fetch_inputs(
    db: Session, application: JobApplication
) -> tuple[Resume | None, JobDescription | None]:
    resume = db.scalar(select(Resume).where(Resume.application_id == application.id))
    job_description = db.scalar(
        select(JobDescription).where(JobDescription.application_id == application.id)
    )
    return resume, job_description


def _hash_for(
    application: JobApplication, resume: Resume, job_description: JobDescription
) -> str:
    return compute_input_hash(
        company_name=application.company_name,
        job_title=application.job_title,
        experience_category=application.experience_category,
        resume_text=resume.extracted_text,
        job_description_text=job_description.content_text,
    )


def _to_read(analysis: ResumeAnalysis, is_outdated: bool) -> AnalysisRead:
    data = AnalysisRead.model_validate(analysis)
    data.is_outdated = is_outdated
    return data


@router.post("", response_model=AnalysisRunResponse)
def run_analysis(
    response: Response,
    force: bool = Query(
        default=False, description="Re-run the LLM even if inputs are unchanged."
    ),
    application: JobApplication = Depends(get_owned_application),
    db: Session = Depends(get_db),
) -> AnalysisRunResponse:
    """Analyze the resume against the job description (201 new, 200 otherwise)."""
    resume, job_description = _fetch_inputs(db, application)

    missing = []
    if resume is None:
        missing.append("resume")
    if job_description is None:
        missing.append("job description")
    if missing:
        raise HTTPException(
            status_code=409,
            detail=f"Missing required input: {' and '.join(missing)}. Add it before running the analysis.",
        )

    if len(resume.extracted_text) > MAX_ANALYSIS_INPUT_CHARS:
        raise HTTPException(
            status_code=422,
            detail=f"Resume text is too long for analysis (maximum {MAX_ANALYSIS_INPUT_CHARS} characters).",
        )
    if len(job_description.content_text) > MAX_ANALYSIS_INPUT_CHARS:
        raise HTTPException(
            status_code=422,
            detail=f"Job description is too long for analysis (maximum {MAX_ANALYSIS_INPUT_CHARS} characters).",
        )

    input_hash = _hash_for(application, resume, job_description)
    existing = db.scalar(
        select(ResumeAnalysis).where(ResumeAnalysis.application_id == application.id)
    )

    # Avoid a duplicate LLM request when nothing has changed.
    if existing is not None and existing.input_hash == input_hash and not force:
        return AnalysisRunResponse(reused=True, analysis=_to_read(existing, False))

    try:
        result = analyze_resume_against_job(
            company_name=application.company_name,
            job_title=application.job_title,
            experience_category=application.experience_category,
            resume_text=resume.extracted_text,
            job_description_text=job_description.content_text,
        )
    except AIServiceError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message)

    fields = {
        "input_hash": input_hash,
        "model_name": settings.groq_model,
        "match_score": compute_match_score(result),  # calculated in Python
        "result": result.model_dump(mode="json"),
    }

    if existing is None:
        existing = ResumeAnalysis(application_id=application.id, **fields)
        db.add(existing)
        response.status_code = 201
    else:
        for name, value in fields.items():
            setattr(existing, name, value)

    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=409, detail="An analysis is already being saved. Try again."
        )

    db.refresh(existing)
    logger.info(
        "Analysis stored: application=%s model=%s score=%s",
        application.id,
        existing.model_name,
        existing.match_score,
    )
    return AnalysisRunResponse(reused=False, analysis=_to_read(existing, False))


@router.get("", response_model=AnalysisRead)
def get_analysis(
    application: JobApplication = Depends(get_owned_application),
    db: Session = Depends(get_db),
) -> AnalysisRead:
    """Return the saved analysis. Never calls the LLM."""
    analysis = db.scalar(
        select(ResumeAnalysis).where(ResumeAnalysis.application_id == application.id)
    )
    if analysis is None:
        raise HTTPException(
            status_code=404, detail="No analysis for this application yet"
        )

    resume, job_description = _fetch_inputs(db, application)
    if resume is None or job_description is None:
        is_outdated = True
    else:
        is_outdated = analysis.input_hash != _hash_for(
            application, resume, job_description
        )
    return _to_read(analysis, is_outdated)