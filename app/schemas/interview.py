import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.question_bank.models import Difficulty, ExperienceCategory

InterviewStatus = Literal["in_progress", "completed"]
EvaluationStatus = Literal["not_started", "in_progress", "completed", "failed"]
EndReason = Literal["finished_by_user", "time_expired"]
InputMethod = Literal["typed", "speech"]


# ---- Requests ----

class InterviewCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    subjects: list[str] | None = Field(
        default=None,
        min_length=1,
        max_length=20,
        description="Subjects to draw from. Omit to practice from your prep checklist.",
    )
    difficulty: list[Difficulty] | None = Field(default=None, min_length=1)
    question_count: int = Field(default=10, ge=1, le=50)
    duration_minutes: int = Field(default=30, ge=5, le=180)


class AnswerSubmit(BaseModel):
    model_config = ConfigDict(extra="forbid")

    position: int = Field(ge=1, description="Position of the question being answered.")
    answer: str = Field(min_length=1, max_length=10_000)
    input_method: InputMethod = "typed"

    @field_validator("answer")
    @classmethod
    def clean_answer(cls, value: str) -> str:
        # PostgreSQL cannot store NUL characters.
        cleaned = value.replace("\x00", "").strip()
        if not cleaned:
            raise ValueError("answer must not be empty")
        return cleaned


class SkipSubmit(BaseModel):
    model_config = ConfigDict(extra="forbid")

    position: int = Field(ge=1)


# ---- Responses ----
# Note: nothing here exposes reference answers or key concepts.

class InterviewQuestionOut(BaseModel):
    position: int
    total_questions: int
    subject: str
    topic: str
    subtopic: str
    difficulty: Difficulty
    question: str
    estimated_time_minutes: float


class InterviewProgress(BaseModel):
    total_questions: int
    answered: int
    skipped: int
    remaining: int


class InterviewRead(BaseModel):
    id: uuid.UUID
    application_id: uuid.UUID
    status: InterviewStatus
    evaluation_status: EvaluationStatus
    end_reason: EndReason | None
    source: Literal["subjects", "checklist"]
    experience_category: ExperienceCategory
    subjects: list[str] | None
    difficulties: list[Difficulty] | None
    requested_question_count: int
    duration_minutes: int
    started_at: datetime
    ends_at: datetime
    finished_at: datetime | None
    remaining_seconds: int | None
    progress: InterviewProgress
    notes: list[str]
    current_question: InterviewQuestionOut | None


class AnswerResult(BaseModel):
    status: InterviewStatus
    remaining_seconds: int | None
    all_answered: bool
    progress: InterviewProgress
    next_question: InterviewQuestionOut | None


class TranscriptItem(BaseModel):
    position: int
    subject: str
    topic: str
    subtopic: str
    difficulty: Difficulty
    question: str
    answer: str | None
    skipped: bool
    input_method: InputMethod | None
    asked_at: datetime | None
    answered_at: datetime | None
    time_taken_seconds: float | None


class TranscriptRead(BaseModel):
    interview_id: uuid.UUID
    status: InterviewStatus
    items: list[TranscriptItem]