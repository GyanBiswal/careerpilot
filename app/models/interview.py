import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class InterviewSession(Base):
    __tablename__ = "interview_sessions"
    __table_args__ = (
        CheckConstraint(
            "status IN ('in_progress', 'completed')",
            name="ck_interview_sessions_status",
        ),
        CheckConstraint(
            "evaluation_status IN ('not_started', 'in_progress', 'completed', 'failed')",
            name="ck_interview_sessions_evaluation_status",
        ),
        CheckConstraint(
            "end_reason IS NULL OR end_reason IN ('finished_by_user', 'time_expired')",
            name="ck_interview_sessions_end_reason",
        ),
        CheckConstraint(
            "source IN ('subjects', 'checklist')",
            name="ck_interview_sessions_source",
        ),
        CheckConstraint(
            "experience_category IN ('fresher', 'experienced')",
            name="ck_interview_sessions_experience_category",
        ),
        # At most one in-progress interview per application, enforced by the database.
        Index(
            "uq_interview_sessions_one_active_per_application",
            "application_id",
            unique=True,
            postgresql_where=text("status = 'in_progress'"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    application_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("job_applications.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    status: Mapped[str] = mapped_column(
        String(20), default="in_progress", server_default="in_progress", nullable=False
    )
    evaluation_status: Mapped[str] = mapped_column(
        String(20), default="not_started", server_default="not_started", nullable=False
    )
    end_reason: Mapped[str | None] = mapped_column(String(20), nullable=True)

    # Configuration (a snapshot of what was requested)
    source: Mapped[str] = mapped_column(String(20), nullable=False)
    experience_category: Mapped[str] = mapped_column(String(20), nullable=False)
    subjects: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    difficulties: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    requested_question_count: Mapped[int] = mapped_column(Integer, nullable=False)
    duration_minutes: Mapped[int] = mapped_column(Integer, nullable=False)

    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    questions: Mapped[list["InterviewQuestion"]] = relationship(
        back_populates="interview",
        order_by="InterviewQuestion.position",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )


class InterviewQuestion(Base):
    """One question in an interview, with the candidate's response.

    The question fields are a snapshot copied from the bank at creation time.
    """

    __tablename__ = "interview_questions"
    __table_args__ = (
        UniqueConstraint("interview_id", "position", name="uq_interview_questions_position"),
        UniqueConstraint(
            "interview_id", "bank_question_id", name="uq_interview_questions_bank_question"
        ),
        CheckConstraint("position >= 1", name="ck_interview_questions_position"),
        CheckConstraint(
            "difficulty IN ('easy', 'medium', 'hard')",
            name="ck_interview_questions_difficulty",
        ),
        CheckConstraint(
            "input_method IS NULL OR input_method IN ('typed', 'speech')",
            name="ck_interview_questions_input_method",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    interview_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("interview_sessions.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False)

    # ---- Snapshot of the bank question ----
    bank_question_id: Mapped[str] = mapped_column(String(100), nullable=False)
    subject: Mapped[str] = mapped_column(String(100), nullable=False)
    topic: Mapped[str] = mapped_column(String(255), nullable=False)
    subtopic: Mapped[str] = mapped_column(String(255), nullable=False)
    difficulty: Mapped[str] = mapped_column(String(10), nullable=False)
    priority: Mapped[str] = mapped_column(String(2), nullable=False)
    question_text: Mapped[str] = mapped_column(Text, nullable=False)
    reference_answer: Mapped[str] = mapped_column(Text, nullable=False)
    key_concepts: Mapped[list] = mapped_column(JSONB, nullable=False)
    estimated_time_minutes: Mapped[float] = mapped_column(Float, nullable=False)

    # ---- The candidate's response ----
    asked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    answered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    answer_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    input_method: Mapped[str | None] = mapped_column(String(10), nullable=True)
    skipped: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="false", nullable=False
    )

    interview: Mapped[InterviewSession] = relationship(back_populates="questions")