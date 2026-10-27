import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.services.document_parser import MAX_TEXT_CHARS


class JobDescriptionTextCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str = Field(min_length=1, max_length=MAX_TEXT_CHARS)


class JobDescriptionRead(BaseModel):
    """Metadata only."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    application_id: uuid.UUID
    source: Literal["text", "pdf", "docx"]
    original_filename: str | None
    page_count: int | None
    character_count: int
    created_at: datetime
    updated_at: datetime


class JobDescriptionDetail(JobDescriptionRead):
    """Metadata plus the full stored text."""

    content_text: str