import logging

from fastapi import APIRouter, Depends, File, HTTPException, Response, UploadFile
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.deps import get_owned_application
from app.core.config import get_settings
from app.db.session import get_db
from app.models.job_application import JobApplication
from app.models.job_description import JobDescription
from app.schemas.job_description import (
    JobDescriptionDetail,
    JobDescriptionRead,
    JobDescriptionTextCreate,
)
from app.services.document_parser import (
    DocumentFileError,
    normalize_text,
    parse_document,
    read_upload,
    sanitize_filename,
)

logger = logging.getLogger("careerpilot.job_descriptions")
settings = get_settings()

MIN_JD_CHARS = 50

router = APIRouter(
    prefix="/applications/{application_id}/job-description",
    tags=["Job Descriptions"],
)


def _check_min_length(text: str) -> None:
    if len(text) < MIN_JD_CHARS:
        raise HTTPException(
            status_code=422,
            detail=f"Job description is too short (minimum {MIN_JD_CHARS} characters).",
        )


def _save(
    db: Session,
    application: JobApplication,
    response: Response,
    fields: dict,
) -> JobDescription:
    """Create (201) or replace (200) the job description for an application."""
    job_description = db.scalar(
        select(JobDescription).where(JobDescription.application_id == application.id)
    )
    if job_description is None:
        job_description = JobDescription(application_id=application.id, **fields)
        db.add(job_description)
        response.status_code = 201
    else:
        for name, value in fields.items():
            setattr(job_description, name, value)

    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=409, detail="A job description save is already in progress."
        )

    db.refresh(job_description)
    logger.info(
        "Job description stored: application=%s source=%s chars=%d",
        application.id,
        job_description.source,
        job_description.character_count,
    )
    return job_description


@router.put("/text", response_model=JobDescriptionRead)
def save_job_description_text(
    payload: JobDescriptionTextCreate,
    response: Response,
    application: JobApplication = Depends(get_owned_application),
    db: Session = Depends(get_db),
) -> JobDescription:
    """Paste a job description as text."""
    text = normalize_text(payload.text)
    _check_min_length(text)

    return _save(
        db,
        application,
        response,
        {
            "source": "text",
            "original_filename": None,
            "page_count": None,
            "content_text": text,
        },
    )


@router.put("/file", response_model=JobDescriptionRead)
def upload_job_description_file(
    response: Response,
    file: UploadFile = File(...),
    application: JobApplication = Depends(get_owned_application),
    db: Session = Depends(get_db),
) -> JobDescription:
    """Upload a job description as a PDF or DOCX file."""
    try:
        data = read_upload(file.file, settings.max_upload_size_mb)
        parsed = parse_document(
            file.filename or "", data, settings.max_document_pages
        )
    except DocumentFileError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message)

    _check_min_length(parsed.text)

    return _save(
        db,
        application,
        response,
        {
            "source": parsed.file_type,
            "original_filename": sanitize_filename(file.filename or "job-description"),
            "page_count": parsed.page_count,
            "content_text": parsed.text,
        },
    )


@router.get("", response_model=JobDescriptionDetail)
def get_job_description(
    application: JobApplication = Depends(get_owned_application),
    db: Session = Depends(get_db),
) -> JobDescription:
    job_description = db.scalar(
        select(JobDescription).where(JobDescription.application_id == application.id)
    )
    if job_description is None:
        raise HTTPException(
            status_code=404, detail="No job description for this application"
        )
    return job_description


@router.delete("", status_code=204)
def delete_job_description(
    application: JobApplication = Depends(get_owned_application),
    db: Session = Depends(get_db),
) -> None:
    job_description = db.scalar(
        select(JobDescription).where(JobDescription.application_id == application.id)
    )
    if job_description is None:
        raise HTTPException(
            status_code=404, detail="No job description for this application"
        )
    db.delete(job_description)
    db.commit()