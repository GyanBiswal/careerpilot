import logging
from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from app.api.deps import get_owned_application, get_owned_interview
from app.db.session import get_db
from app.interview.selection import select_interview_questions
from app.interview.service import (
    build_progress,
    current_question,
    expire_if_needed,
    now_utc,
    question_out,
    remaining_seconds,
    to_read,
)
from app.models.checklist import PrepChecklist
from app.models.interview import InterviewQuestion, InterviewSession
from app.models.job_application import JobApplication
from app.question_bank.filters import filter_questions
from app.question_bank.loader import get_store
from app.question_bank.models import StoredQuestion, normalize_subject
from app.schemas.interview import (
    AnswerResult,
    AnswerSubmit,
    InterviewCreate,
    InterviewRead,
    SkipSubmit,
    TranscriptItem,
    TranscriptRead,
)

logger = logging.getLogger("careerpilot.interviews")

router = APIRouter(
    prefix="/applications/{application_id}/interviews", tags=["Interviews"]
)


def _build_pool(
    db: Session, application: JobApplication, payload: InterviewCreate
) -> tuple[str, list[str] | None, list[StoredQuestion]]:
    """Return (source, normalized subjects, candidate questions)."""
    store = get_store()
    if not store.questions:
        raise HTTPException(
            status_code=409,
            detail="No question banks are loaded. Add JSON files to data/question_banks/ and reload.",
        )
    category = application.experience_category

    if payload.subjects:
        subjects = sorted(
            {s for s in (normalize_subject(x) for x in payload.subjects) if s}
        )
        known = {q.subject for q in store.questions}
        unknown = [s for s in subjects if s not in known]
        if not subjects or unknown:
            raise HTTPException(
                status_code=422,
                detail=(
                    f"Unknown subject(s): {', '.join(unknown) or '(empty)'}. "
                    f"Available subjects: {', '.join(sorted(known))}."
                ),
            )
        pool = filter_questions(
            store.questions,
            subjects=subjects,
            difficulties=payload.difficulty,
            experience_category=category,
        )
        return "subjects", subjects, pool

    # No subjects given: practice from the prep checklist.
    checklist = db.scalar(
        select(PrepChecklist).where(PrepChecklist.application_id == application.id)
    )
    if checklist is None:
        raise HTTPException(
            status_code=422,
            detail="Choose at least one subject, or generate a checklist first and leave 'subjects' out to practice from it.",
        )
    question_ids = dict.fromkeys(
        question_id
        for item in checklist.items
        for question_id in item.get("question_ids", [])
    )
    allowed_difficulties = set(payload.difficulty) if payload.difficulty else None
    pool = [
        store.by_id[question_id]
        for question_id in question_ids
        if question_id in store.by_id
        and store.by_id[question_id].experience_category == category
        and (allowed_difficulties is None or store.by_id[question_id].difficulty in allowed_difficulties)
    ]
    return "checklist", None, pool


@router.post("", response_model=InterviewRead, status_code=201)
def create_interview(
    payload: InterviewCreate,
    application: JobApplication = Depends(get_owned_application),
    db: Session = Depends(get_db),
) -> InterviewRead:
    """Start a mock interview and return its first question."""
    active = db.scalar(
        select(InterviewSession).where(
            InterviewSession.application_id == application.id,
            InterviewSession.status == "in_progress",
        )
    )
    if active is not None:
        if expire_if_needed(active):
            db.commit()  # its time had run out, so it is closed and a new one may start
        else:
            raise HTTPException(
                status_code=409,
                detail=f"An interview is already in progress for this application (id: {active.id}). Finish it before starting another.",
            )

    source, subjects, pool = _build_pool(db, application, payload)

    # Prefer questions this application's candidate hasn't been asked before.
    previously_asked = set(
        db.scalars(
            select(InterviewQuestion.bank_question_id)
            .join(InterviewSession, InterviewQuestion.interview_id == InterviewSession.id)
            .where(
                InterviewSession.application_id == application.id,
                InterviewQuestion.asked_at.is_not(None),
            )
        )
    )
    chosen = select_interview_questions(
        pool, payload.question_count, previously_asked_ids=previously_asked
    )
    if not chosen:
        raise HTTPException(
            status_code=422,
            detail=f"No questions match these settings for a {application.experience_category} candidate. Try other subjects or difficulties.",
        )

    now = now_utc()
    interview = InterviewSession(
        application_id=application.id,
        source=source,
        experience_category=application.experience_category,
        subjects=subjects,
        difficulties=list(dict.fromkeys(payload.difficulty)) if payload.difficulty else None,
        requested_question_count=payload.question_count,
        duration_minutes=payload.duration_minutes,
        started_at=now,
        ends_at=now + timedelta(minutes=payload.duration_minutes),
    )
    for position, question in enumerate(chosen, start=1):
        interview.questions.append(
            InterviewQuestion(
                position=position,
                bank_question_id=question.id,
                subject=question.subject,
                topic=question.topic,
                subtopic=question.subtopic,
                difficulty=question.difficulty,
                priority=question.priority,
                question_text=question.question,
                reference_answer=question.sample_answer,
                key_concepts=list(question.key_concepts),
                estimated_time_minutes=float(question.estimated_time_minutes),
            )
        )
    first = interview.questions[0]
    first.asked_at = now  # the first question is served in this response

    db.add(interview)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="An interview is already in progress for this application.",
        )

    logger.info(
        "Interview started: id=%s application=%s source=%s questions=%d",
        interview.id,
        application.id,
        source,
        len(chosen),
    )
    return to_read(interview, first)


@router.get("", response_model=list[InterviewRead])
def list_interviews(
    application: JobApplication = Depends(get_owned_application),
    db: Session = Depends(get_db),
) -> list[InterviewRead]:
    """Interview history for this application, newest first."""
    interviews = db.scalars(
        select(InterviewSession)
        .where(InterviewSession.application_id == application.id)
        .options(selectinload(InterviewSession.questions))
        .order_by(InterviewSession.started_at.desc())
    ).all()

    changed = [expire_if_needed(i) for i in interviews]  # evaluate every interview
    if any(changed):
        db.commit()
    return [to_read(i, None) for i in interviews]


@router.get("/{interview_id}", response_model=InterviewRead)
def get_interview(
    interview: InterviewSession = Depends(get_owned_interview),
    db: Session = Depends(get_db),
) -> InterviewRead:
    """Current state. For an in-progress interview this also resumes it: the
    current question is returned again."""
    changed = expire_if_needed(interview)

    current = current_question(interview) if interview.status == "in_progress" else None
    if current is not None and current.asked_at is None:
        current.asked_at = now_utc()
        changed = True

    if changed:
        db.commit()
    return to_read(interview, current)


def _record_response(
    db: Session,
    interview: InterviewSession,
    position: int,
    *,
    answer: str | None,
    input_method: str | None,
    skipped: bool,
) -> AnswerResult:
    # Lock the interview row so simultaneous submissions are handled one at a time.
    db.refresh(interview, with_for_update=True)

    expired = expire_if_needed(interview)
    if interview.status != "in_progress":
        if expired:
            db.commit()
        raise HTTPException(
            status_code=409,
            detail=f"Interview is not in progress (status: {interview.status}).",
        )

    current = current_question(interview)
    if current is None:
        raise HTTPException(
            status_code=409,
            detail="All questions have already been answered. Finish the interview.",
        )
    if position != current.position:
        raise HTTPException(
            status_code=409,
            detail=f"Question {position} is not the current question (the current one is {current.position}).",
        )

    now = now_utc()
    if current.asked_at is None:
        current.asked_at = now
    current.answered_at = now
    current.answer_text = answer
    current.input_method = input_method
    current.skipped = skipped

    following = current_question(interview)
    if following is not None and following.asked_at is None:
        following.asked_at = now  # served to the candidate in this response

    db.commit()

    # Never log answer text: it is personal data.
    logger.info(
        "Interview response saved: interview=%s position=%d skipped=%s",
        interview.id,
        position,
        skipped,
    )
    return AnswerResult(
        status=interview.status,
        remaining_seconds=remaining_seconds(interview),
        all_answered=following is None,
        progress=build_progress(interview),
        next_question=(
            question_out(following, len(interview.questions)) if following else None
        ),
    )


@router.post("/{interview_id}/answer", response_model=AnswerResult)
def submit_answer(
    payload: AnswerSubmit,
    interview: InterviewSession = Depends(get_owned_interview),
    db: Session = Depends(get_db),
) -> AnswerResult:
    """Save the answer to the current question. No feedback is given here."""
    return _record_response(
        db,
        interview,
        payload.position,
        answer=payload.answer,
        input_method=payload.input_method,
        skipped=False,
    )


@router.post("/{interview_id}/skip", response_model=AnswerResult)
def skip_question(
    payload: SkipSubmit,
    interview: InterviewSession = Depends(get_owned_interview),
    db: Session = Depends(get_db),
) -> AnswerResult:
    """Skip the current question."""
    return _record_response(
        db,
        interview,
        payload.position,
        answer=None,
        input_method=None,
        skipped=True,
    )


@router.post("/{interview_id}/finish", response_model=InterviewRead)
def finish_interview(
    interview: InterviewSession = Depends(get_owned_interview),
    db: Session = Depends(get_db),
) -> InterviewRead:
    """End the interview. Safe to call more than once."""
    db.refresh(interview, with_for_update=True)
    expire_if_needed(interview)

    if interview.status == "in_progress":
        interview.status = "completed"
        interview.finished_at = now_utc()
        interview.end_reason = "finished_by_user"
        logger.info("Interview finished: id=%s", interview.id)

    db.commit()
    return to_read(interview, None)


@router.get("/{interview_id}/transcript", response_model=TranscriptRead)
def get_transcript(
    interview: InterviewSession = Depends(get_owned_interview),
    db: Session = Depends(get_db),
) -> TranscriptRead:
    """Questions and saved answers with timestamps. Questions not yet asked are
    hidden while the interview is in progress. No reference answers, no scores."""
    if expire_if_needed(interview):
        db.commit()

    items = []
    for question in interview.questions:
        if interview.status == "in_progress" and question.asked_at is None:
            continue
        time_taken = None
        if question.asked_at and question.answered_at:
            time_taken = round(
                (question.answered_at - question.asked_at).total_seconds(), 1
            )
        items.append(
            TranscriptItem(
                position=question.position,
                subject=question.subject,
                topic=question.topic,
                subtopic=question.subtopic,
                difficulty=question.difficulty,
                question=question.question_text,
                answer=question.answer_text,
                skipped=question.skipped,
                input_method=question.input_method,
                asked_at=question.asked_at,
                answered_at=question.answered_at,
                time_taken_seconds=time_taken,
            )
        )
    return TranscriptRead(
        interview_id=interview.id, status=interview.status, items=items
    )