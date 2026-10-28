from collections import Counter, defaultdict

from fastapi import APIRouter, Depends, HTTPException, Query

from app.api.deps import get_current_user
from app.core.config import get_settings
from app.question_bank.filters import filter_questions
from app.question_bank.loader import get_store, reload_store
from app.question_bank.models import (
    Difficulty,
    ExperienceCategory,
    Priority,
    QuestionBankStore,
    StoredQuestion,
)
from app.schemas.question_bank import (
    BankOverview,
    DiagnosticsResponse,
    FileInfoRead,
    IssueRead,
    QuestionDetail,
    QuestionListResponse,
    QuestionSummary,
    SubjectSummary,
)

settings = get_settings()

# Every endpoint here requires a logged-in user.
router = APIRouter(
    prefix="/question-banks",
    tags=["Question Banks"],
    dependencies=[Depends(get_current_user)],
)


def _require_development() -> None:
    """Diagnostics expose file names and validation details, so they are
    development-only until the app has admin roles."""
    if settings.app_env != "development":
        raise HTTPException(status_code=404, detail="Not found")


def _diagnostics(store: QuestionBankStore) -> DiagnosticsResponse:
    return DiagnosticsResponse(
        directory=store.directory,
        file_count=len(store.files),
        total_questions=len(store.questions),
        error_count=store.error_count,
        warning_count=store.warning_count,
        files=[FileInfoRead.model_validate(f) for f in store.files],
        issues=[IssueRead.model_validate(i) for i in store.issues],
    )


@router.get("", response_model=BankOverview)
def get_overview() -> BankOverview:
    """Which subjects are loaded, with counts and available topics/roles."""
    store = get_store()

    by_subject: dict[str, list[StoredQuestion]] = defaultdict(list)
    for q in store.questions:
        by_subject[q.subject].append(q)

    subjects = [
        SubjectSummary(
            subject=subject,
            question_count=len(items),
            by_experience_category=dict(Counter(q.experience_category for q in items)),
            by_difficulty=dict(Counter(q.difficulty for q in items)),
            topics=sorted({q.topic for q in items}),
        )
        for subject, items in sorted(by_subject.items())
    ]
    roles = sorted({r for q in store.questions for r in q.role_tags}, key=str.lower)

    return BankOverview(
        total_questions=len(store.questions),
        subject_count=len(subjects),
        roles=roles,
        subjects=subjects,
    )


@router.get("/questions", response_model=QuestionListResponse)
def list_questions(
    subject: list[str] | None = Query(default=None),
    topic: list[str] | None = Query(default=None),
    subtopic: list[str] | None = Query(default=None),
    difficulty: list[Difficulty] | None = Query(default=None),
    experience_category: ExperienceCategory | None = Query(default=None),
    role: list[str] | None = Query(default=None),
    priority: list[Priority] | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> QuestionListResponse:
    """Filter questions. Repeat a parameter to allow several values."""
    matches = filter_questions(
        get_store().questions,
        subjects=subject,
        topics=topic,
        subtopics=subtopic,
        difficulties=difficulty,
        experience_category=experience_category,
        roles=role,
        priorities=priority,
    )
    page = matches[offset : offset + limit]
    return QuestionListResponse(
        total=len(matches),
        limit=limit,
        offset=offset,
        items=[QuestionSummary.model_validate(q) for q in page],
    )


@router.get("/questions/{question_id}", response_model=QuestionDetail)
def get_question(question_id: str) -> StoredQuestion:
    question = get_store().by_id.get(question_id)
    if question is None:
        raise HTTPException(status_code=404, detail="Question not found")
    return question


@router.get("/diagnostics", response_model=DiagnosticsResponse)
def get_diagnostics() -> DiagnosticsResponse:
    """Validation report for the loaded files (development only)."""
    _require_development()
    return _diagnostics(get_store())


@router.post("/reload", response_model=DiagnosticsResponse)
def reload_question_banks() -> DiagnosticsResponse:
    """Rescan the directory without restarting the server (development only)."""
    _require_development()
    return _diagnostics(reload_store())