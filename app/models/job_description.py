import uuid
from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class JobDescription(Base):
    __tablename__ = "job_descriptions"
    __table_args__ = (
        CheckConstraint(
            "source IN ('text', 'pdf', 'docx')", name="ck_job_descriptions_source"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    # unique=True enforces "one job description per application".
    application_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("job_applications.id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
    )
    source: Mapped[str] = mapped_column(String(10), nullable=False)
    original_filename: Mapped[str | None] = mapped_column(String(255), nullable=True)
    page_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    content_text: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    @property
    def character_count(self) -> int:
        return len(self.content_text)