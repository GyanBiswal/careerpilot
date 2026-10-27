import logging

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_owned_application
from app.db.session import get_db
from app.models.job_application import JobApplication
from app.models.user import User
from app.schemas.application import (
    ApplicationCreate,
    ApplicationRead,
    ApplicationStatus,
    ApplicationUpdate,
)

logger = logging.getLogger("careerpilot.applications")

router = APIRouter(prefix="/applications", tags=["Applications"])


@router.post("", response_model=ApplicationRead, status_code=201)
def create_application(
    payload: ApplicationCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> JobApplication:
    application = JobApplication(user_id=current_user.id, **payload.model_dump())
    db.add(application)
    db.commit()
    db.refresh(application)
    logger.info(
        "Application created: id=%s user=%s", application.id, current_user.id
    )
    return application


@router.get("", response_model=list[ApplicationRead])
def list_applications(
    status_filter: ApplicationStatus | None = Query(default=None, alias="status"),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[JobApplication]:
    stmt = select(JobApplication).where(JobApplication.user_id == current_user.id)
    if status_filter is not None:
        stmt = stmt.where(JobApplication.status == status_filter)
    stmt = (
        stmt.order_by(JobApplication.created_at.desc(), JobApplication.id)
        .limit(limit)
        .offset(offset)
    )
    return list(db.scalars(stmt))


@router.get("/{application_id}", response_model=ApplicationRead)
def get_application(
    application: JobApplication = Depends(get_owned_application),
) -> JobApplication:
    return application


@router.patch("/{application_id}", response_model=ApplicationRead)
def update_application(
    payload: ApplicationUpdate,
    application: JobApplication = Depends(get_owned_application),
    db: Session = Depends(get_db),
) -> JobApplication:
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(application, field, value)
    db.commit()
    db.refresh(application)
    return application


@router.delete("/{application_id}", status_code=204)
def delete_application(
    application: JobApplication = Depends(get_owned_application),
    db: Session = Depends(get_db),
) -> None:
    db.delete(application)
    db.commit()
    logger.info("Application deleted: id=%s", application.id)