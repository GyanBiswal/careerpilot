import hashlib
import logging
from collections import Counter

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.deps import get_owned_application
from app.checklist.builder import build_checklist, derive_topics
from app.checklist.matching import load_aliases
from app.db.session import get_db
from app.models.analysis import ResumeAnalysis
from app.models.checklist import PrepChecklist
from app.models.job_application import JobApplication
from app.question_bank.loader import get_store
from app.question_bank.models import StoredQuestion
from app.schemas.analysis import ResumeJDAnalysis
from app.schemas.checklist import (
    ChecklistGenerateRequest,
    ChecklistItem,
    ChecklistItemRead,
    ChecklistRead,
    ChecklistSettings,
    ChecklistSummary,
)
from app.schemas.question_bank import QuestionSummary

logger = logging.getLogger("careerpilot.checklist")

router = APIRouter(
    prefix="/applications/{application_id}/checklist", tags=["Checklist"]
)


def _get_analysis(db: Session, application: JobApplication) -> ResumeAnalysis | None:
    return db.scalar(
        select(ResumeAnalysis).where(ResumeAnalysis.application_id == application.id)
    )


def _source_hash(analysis: ResumeAnalysis, application: JobApplication) -> str:
    # updated_at changes whenever the analysis result is replaced.
    marker = f"{analysis.updated_at.isoformat()}|{application.experience_category}"
    return hashlib.sha256(marker.encode("utf-8")).hexdigest()


def _build_read(
    record: PrepChecklist,
    application: JobApplication,
    analysis: ResumeAnalysis | None,
) -> ChecklistRead:
    """Resolve stored question IDs against the current banks (no LLM, no DB writes)."""
    store = get_store()
    items: list[ChecklistItemRead] = []
    distinct: dict[str, StoredQuestion] = {}

    for raw in record.items:
        item = ChecklistItem.model_validate(raw)
        questions: list[QuestionSummary] = []
        missing: list[str] = []
        for question_id in item.question_ids:
            question = store.by_id.get(question_id)
            if question is None:
                missing.append(question_id)
            else:
                distinct[question_id] = question
                questions.append(QuestionSummary.model_validate(question))
        items.append(
            ChecklistItemRead(
                **item.model_dump(), questions=questions, missing_question_ids=missing
            )
        )

    statuses = Counter(i.status for i in items)
    summary = ChecklistSummary(
        topic_count=len(items),
        covered=statuses["covered"],
        partial=statuses["partial"],
        uncovered=statuses["uncovered"],
        distinct_question_count=len(distinct),
        estimated_total_minutes=round(
            sum(q.estimated_time_minutes for q in distinct.values()), 1
        ),
    )
    is_outdated = analysis is None or record.source_hash != _source_hash(
        analysis, application
    )

    return ChecklistRead(
        id=record.id,
        application_id=record.application_id,
        experience_category=record.experience_category,
        is_outdated=is_outdated,
        created_at=record.created_at,
        updated_at=record.updated_at,
        settings=ChecklistSettings.model_validate(record.settings),
        summary=summary,
        gaps=[i.topic for i in items if i.status == "uncovered"],
        items=items,
    )


@router.post("", response_model=ChecklistRead)
def generate_checklist(
    response: Response,
    payload: ChecklistGenerateRequest | None = None,
    application: JobApplication = Depends(get_owned_application),
    db: Session = Depends(get_db),
) -> ChecklistRead:
    """Generate (201) or regenerate (200) the checklist. Uses no LLM."""
    options = payload or ChecklistGenerateRequest()

    analysis = _get_analysis(db, application)
    if analysis is None:
        raise HTTPException(
            status_code=409,
            detail="Run the resume/job description analysis first.",
        )

    store = get_store()
    if not store.questions:
        raise HTTPException(
            status_code=409,
            detail="No question banks are loaded. Add JSON files to data/question_banks/ and reload.",
        )

    aliases = load_aliases()
    topics = derive_topics(ResumeJDAnalysis.model_validate(analysis.result), aliases)
    items = build_checklist(
        topics,
        store.questions,
        experience_category=application.experience_category,
        difficulties=options.difficulty,
        questions_per_topic=options.questions_per_topic,
        aliases=aliases,
    )

    fields = {
        "source_hash": _source_hash(analysis, application),
        "experience_category": application.experience_category,
        "settings": ChecklistSettings(
            difficulty=options.difficulty,
            questions_per_topic=options.questions_per_topic,
        ).model_dump(mode="json"),
        "items": [item.model_dump(mode="json") for item in items],
    }

    record = db.scalar(
        select(PrepChecklist).where(PrepChecklist.application_id == application.id)
    )
    if record is None:
        record = PrepChecklist(application_id=application.id, **fields)
        db.add(record)
        response.status_code = 201
    else:
        for name, value in fields.items():
            setattr(record, name, value)

    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=409, detail="A checklist is already being saved. Try again."
        )

    db.refresh(record)
    logger.info(
        "Checklist stored: application=%s topics=%d", application.id, len(items)
    )
    return _build_read(record, application, analysis)


@router.get("", response_model=ChecklistRead)
def get_checklist(
    application: JobApplication = Depends(get_owned_application),
    db: Session = Depends(get_db),
) -> ChecklistRead:
    record = db.scalar(
        select(PrepChecklist).where(PrepChecklist.application_id == application.id)
    )
    if record is None:
        raise HTTPException(status_code=404, detail="No checklist for this application yet")
    return _build_read(record, application, _get_analysis(db, application))


@router.delete("", status_code=204)
def delete_checklist(
    application: JobApplication = Depends(get_owned_application),
    db: Session = Depends(get_db),
) -> None:
    record = db.scalar(
        select(PrepChecklist).where(PrepChecklist.application_id == application.id)
    )
    if record is None:
        raise HTTPException(status_code=404, detail="No checklist for this application yet")
    db.delete(record)
    db.commit()