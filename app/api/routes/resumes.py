import hashlib
import logging

from fastapi import APIRouter, Depends, File, HTTPException, Response, UploadFile
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.deps import get_owned_application
from app.core.config import get_settings
from app.db.session import get_db
from app.models.job_application import JobApplication
from app.models.resume import Resume
from app.schemas.resume import ResumeDetail, ResumeRead
from app.services.resume_parser import (
    ResumeFileError,
    parse_resume,
    sanitize_filename,
)

logger = logging.getLogger("careerpilot.resumes")
settings = get_settings()

router = APIRouter(
    prefix="/applications/{application_id}/resume", tags=["Resumes"]
)


def _get_resume_or_404(db: Session, application: JobApplication) -> Resume:
    resume = db.scalar(select(Resume).where(Resume.application_id == application.id))
    if resume is None:
        raise HTTPException(
            status_code=404, detail="No resume uploaded for this application"
        )
    return resume


@router.put("", response_model=ResumeRead)
def upload_resume(
    response: Response,
    file: UploadFile = File(...),
    application: JobApplication = Depends(get_owned_application),
    db: Session = Depends(get_db),
) -> Resume:
    """Upload (201) or replace (200) the resume for this application."""
    max_bytes = settings.max_upload_size_mb * 1024 * 1024

    # Read one byte past the limit so oversized files are detected cheaply.
    data = file.file.read(max_bytes + 1)
    if len(data) > max_bytes:
        raise HTTPException(
            status_code=413,
            detail=f"File too large. Maximum size is {settings.max_upload_size_mb} MB.",
        )
    if not data:
        raise HTTPException(status_code=422, detail="Uploaded file is empty.")

    try:
        parsed = parse_resume(file.filename or "", data, settings.max_resume_pages)
    except ResumeFileError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message)

    fields = {
        "original_filename": sanitize_filename(file.filename or ""),
        "file_type": parsed.file_type,
        "file_size_bytes": len(data),
        "page_count": parsed.page_count,
        "content_sha256": hashlib.sha256(data).hexdigest(),
        "extracted_text": parsed.text,
    }

    resume = db.scalar(select(Resume).where(Resume.application_id == application.id))
    if resume is None:
        resume = Resume(application_id=application.id, **fields)
        db.add(resume)
        response.status_code = 201
    else:
        for name, value in fields.items():
            setattr(resume, name, value)

    try:
        db.commit()
    except IntegrityError:
        # Two simultaneous first uploads: the unique constraint wins.
        db.rollback()
        raise HTTPException(
            status_code=409, detail="A resume upload is already in progress."
        )

    db.refresh(resume)
    logger.info(
        "Resume stored: application=%s type=%s size=%d",
        application.id,
        resume.file_type,
        resume.file_size_bytes,
    )
    return resume


@router.get("", response_model=ResumeDetail)
def get_resume(
    application: JobApplication = Depends(get_owned_application),
    db: Session = Depends(get_db),
) -> Resume:
    return _get_resume_or_404(db, application)


@router.delete("", status_code=204)
def delete_resume(
    application: JobApplication = Depends(get_owned_application),
    db: Session = Depends(get_db),
) -> None:
    resume = _get_resume_or_404(db, application)
    db.delete(resume)
    db.commit()