import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.question_bank.models import Difficulty, ExperienceCategory, Priority
from app.schemas.question_bank import QuestionSummary

ChecklistSource = Literal["analysis", "skill_gap", "general"]
ChecklistStatus = Literal["covered", "partial", "uncovered"]


class ChecklistGenerateRequest(BaseModel):
    """Optional body for POST. Send nothing to use the defaults."""

    model_config = ConfigDict(extra="forbid")

    difficulty: list[Difficulty] | None = Field(
        default=None, description="Only select questions of these difficulties."
    )
    questions_per_topic: int | None = Field(
        default=None, ge=1, le=10,
        description="Override the default (P1: 5, P2: 3, P3: 2).",
    )


class ChecklistSettings(BaseModel):
    difficulty: list[Difficulty] | None
    questions_per_topic: int | None


class ChecklistItem(BaseModel):
    """One topic as stored: question IDs only, no question text."""

    topic: str
    priority: Priority
    source: ChecklistSource
    reason: str
    status: ChecklistStatus
    matched_subjects: list[str]
    target_count: int
    available_count: int
    note: str | None
    question_ids: list[str]


class ChecklistItemRead(ChecklistItem):
    """One topic as returned: question IDs resolved against the current banks."""

    questions: list[QuestionSummary]
    missing_question_ids: list[str]


class ChecklistSummary(BaseModel):
    topic_count: int
    covered: int
    partial: int
    uncovered: int
    distinct_question_count: int
    estimated_total_minutes: float


class ChecklistRead(BaseModel):
    id: uuid.UUID
    application_id: uuid.UUID
    experience_category: ExperienceCategory
    is_outdated: bool = Field(
        description="True if the analysis or experience category changed since this checklist was generated."
    )
    created_at: datetime
    updated_at: datetime
    settings: ChecklistSettings
    summary: ChecklistSummary
    gaps: list[str] = Field(description="Topics with no matching questions in the loaded banks.")
    items: list[ChecklistItemRead]