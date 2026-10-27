import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class ResumeRead(BaseModel):
    """Metadata only: returned after an upload."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    application_id: uuid.UUID
    original_filename: str
    file_type: str
    file_size_bytes: int
    page_count: int | None
    character_count: int
    created_at: datetime
    updated_at: datetime


class ResumeDetail(ResumeRead):
    """Metadata plus the full extracted text."""

    extracted_text: str