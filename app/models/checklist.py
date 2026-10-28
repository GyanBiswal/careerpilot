import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class PrepChecklist(Base):
    __tablename__ = "prep_checklists"
    __table_args__ = (
        CheckConstraint(
            "experience_category IN ('fresher', 'experienced')",
            name="ck_prep_checklists_experience_category",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    # unique=True: one (latest) checklist per application.
    application_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("job_applications.id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
    )
    # Identifies which analysis + experience category this checklist was built from.
    source_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    experience_category: Mapped[str] = mapped_column(String(20), nullable=False)
    settings: Mapped[dict] = mapped_column(JSONB, nullable=False)
    # Topic items containing question IDs only (questions stay in the banks).
    items: Mapped[list] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )