"""Data models for question banks: the file schema and the in-memory store."""
import re
from dataclasses import dataclass, field
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StrictFloat, StrictInt, StringConstraints

Difficulty = Literal["easy", "medium", "hard"]
Priority = Literal["P1", "P2", "P3"]
ExperienceCategory = Literal["fresher", "experienced"]

Text = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
QuestionId = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        min_length=1,
        max_length=100,
        pattern=r"^[A-Za-z0-9_\-]+$",
    ),
]


def normalize_subject(value: str) -> str:
    """'Node.js Express' -> 'node_js_express'; used for filenames and filters."""
    return re.sub(r"[^a-z0-9]+", "_", value.strip().lower()).strip("_")


class Question(BaseModel):
    """The schema every question in a bank file must follow."""

    # extra="forbid" catches typos and banned fields such as min_experience_level.
    model_config = ConfigDict(extra="forbid")

    id: QuestionId
    topic: Text
    subtopic: Text
    difficulty: Difficulty
    priority: Priority
    experience_category: ExperienceCategory
    role_tags: list[Text]
    question: Text
    sample_answer: Text
    key_concepts: list[Text]
    follow_up_questions: list[Text]
    # Strict types: a string like "3" is rejected instead of silently converted.
    estimated_time_minutes: Annotated[StrictInt | StrictFloat, Field(gt=0, le=120)]


class StoredQuestion(Question):
    """A validated question plus where it came from."""

    subject: str
    source_file: str


@dataclass(frozen=True)
class LoadIssue:
    severity: str  # "error" or "warning"
    file: str | None
    location: str | None  # e.g. "question #3 (id=react_003)"
    message: str


@dataclass(frozen=True)
class BankFileInfo:
    file: str
    subject: str
    valid_questions: int
    rejected_questions: int


@dataclass
class QuestionBankStore:
    directory: str
    questions: list[StoredQuestion] = field(default_factory=list)
    by_id: dict[str, StoredQuestion] = field(default_factory=dict)
    files: list[BankFileInfo] = field(default_factory=list)
    issues: list[LoadIssue] = field(default_factory=list)

    @property
    def error_count(self) -> int:
        return sum(1 for i in self.issues if i.severity == "error")

    @property
    def warning_count(self) -> int:
        return sum(1 for i in self.issues if i.severity == "warning")