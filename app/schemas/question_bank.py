from pydantic import BaseModel, ConfigDict

from app.question_bank.models import Difficulty, ExperienceCategory, Priority


class QuestionSummary(BaseModel):
    """List view: deliberately excludes reference answers."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    subject: str
    topic: str
    subtopic: str
    difficulty: Difficulty
    priority: Priority
    experience_category: ExperienceCategory
    role_tags: list[str]
    question: str
    estimated_time_minutes: float


class QuestionDetail(QuestionSummary):
    """Full view for a single question, including the reference answer."""

    sample_answer: str
    key_concepts: list[str]
    follow_up_questions: list[str]


class QuestionListResponse(BaseModel):
    total: int
    limit: int
    offset: int
    items: list[QuestionSummary]


class SubjectSummary(BaseModel):
    subject: str
    question_count: int
    by_experience_category: dict[str, int]
    by_difficulty: dict[str, int]
    topics: list[str]


class BankOverview(BaseModel):
    total_questions: int
    subject_count: int
    roles: list[str]
    subjects: list[SubjectSummary]


class IssueRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    severity: str
    file: str | None
    location: str | None
    message: str


class FileInfoRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    file: str
    subject: str
    valid_questions: int
    rejected_questions: int


class DiagnosticsResponse(BaseModel):
    directory: str
    file_count: int
    total_questions: int
    error_count: int
    warning_count: int
    files: list[FileInfoRead]
    issues: list[IssueRead]