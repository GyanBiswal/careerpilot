import uuid
from datetime import datetime
from typing import Annotated, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    field_validator,
)

ExperienceCategory = Literal["fresher", "experienced"]
ApplicationStatus = Literal[
    "preparing", "applied", "interviewing", "offer", "rejected"
]
Name = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=255)
]


class ApplicationCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    company_name: Name
    job_title: Name
    experience_category: ExperienceCategory
    status: ApplicationStatus = "preparing"
    notes: str | None = Field(default=None, max_length=5000)


class ApplicationUpdate(BaseModel):
    """All fields optional (PATCH). Only fields that are sent get changed."""

    model_config = ConfigDict(extra="forbid")

    company_name: Name | None = None
    job_title: Name | None = None
    experience_category: ExperienceCategory | None = None
    status: ApplicationStatus | None = None
    notes: str | None = Field(default=None, max_length=5000)

    @field_validator(
        "company_name", "job_title", "experience_category", "status", mode="before"
    )
    @classmethod
    def reject_explicit_null(cls, value):
        # These columns are NOT NULL; only `notes` may be cleared with null.
        if value is None:
            raise ValueError("this field cannot be null")
        return value


class ApplicationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    company_name: str
    job_title: str
    experience_category: ExperienceCategory
    status: ApplicationStatus
    notes: str | None
    created_at: datetime
    updated_at: datetime