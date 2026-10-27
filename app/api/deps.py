import uuid

from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import decode_access_token
from app.db.session import get_db
from app.models.job_application import JobApplication
from app.models.user import User

bearer_scheme = HTTPBearer(auto_error=False)


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> User:
    """Resolve the logged-in user from the Authorization: Bearer header."""
    unauthorized = HTTPException(
        status_code=401,
        detail="Not authenticated",
        headers={"WWW-Authenticate": "Bearer"},
    )

    if credentials is None:
        raise unauthorized

    subject = decode_access_token(credentials.credentials)
    if subject is None:
        raise unauthorized

    try:
        user_id = uuid.UUID(subject)
    except ValueError:
        raise unauthorized

    user = db.get(User, user_id)
    if user is None:
        raise unauthorized
    if not user.is_active:
        raise HTTPException(status_code=403, detail="Inactive user")
    return user


def get_owned_application(
    application_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> JobApplication:
    """Load an application only if it belongs to the logged-in user.

    Filtering by BOTH id and user_id means another user's application looks
    exactly like one that doesn't exist (404), so existence is never leaked.
    Later phases (resumes, interviews) will depend on this too.
    """
    application = db.scalar(
        select(JobApplication).where(
            JobApplication.id == application_id,
            JobApplication.user_id == current_user.id,
        )
    )
    if application is None:
        raise HTTPException(status_code=404, detail="Application not found")
    return application