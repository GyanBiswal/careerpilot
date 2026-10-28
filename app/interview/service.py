"""Helpers for interview state: expiry, progress, and response building."""
from datetime import datetime, timedelta, timezone

from app.models.interview import InterviewQuestion, InterviewSession
from app.schemas.interview import (
    InterviewProgress,
    InterviewQuestionOut,
    InterviewRead,
)

# Answers are still accepted this long after ends_at (network delays, slow typing).
GRACE_SECONDS = 30


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def expire_if_needed(interview: InterviewSession) -> bool:
    """Close the interview if its time is up. Returns True if it changed.

    There is no background job: any request that touches the interview after
    the deadline closes it. The caller is responsible for committing.
    """
    if interview.status != "in_progress":
        return False
    if now_utc() <= interview.ends_at + timedelta(seconds=GRACE_SECONDS):
        return False
    interview.status = "completed"
    interview.finished_at = interview.ends_at
    interview.end_reason = "time_expired"
    return True


def current_question(interview: InterviewSession) -> InterviewQuestion | None:
    """The first question that has not been answered or skipped yet."""
    for question in interview.questions:
        if question.answered_at is None:
            return question
    return None


def build_progress(interview: InterviewSession) -> InterviewProgress:
    total = len(interview.questions)
    skipped = sum(1 for q in interview.questions if q.skipped)
    answered = sum(
        1 for q in interview.questions if q.answered_at is not None and not q.skipped
    )
    return InterviewProgress(
        total_questions=total,
        answered=answered,
        skipped=skipped,
        remaining=total - answered - skipped,
    )


def remaining_seconds(interview: InterviewSession) -> int | None:
    if interview.status != "in_progress":
        return None
    return max(0, int((interview.ends_at - now_utc()).total_seconds()))


def question_out(question: InterviewQuestion, total: int) -> InterviewQuestionOut:
    return InterviewQuestionOut(
        position=question.position,
        total_questions=total,
        subject=question.subject,
        topic=question.topic,
        subtopic=question.subtopic,
        difficulty=question.difficulty,
        question=question.question_text,
        estimated_time_minutes=question.estimated_time_minutes,
    )


def to_read(
    interview: InterviewSession, current: InterviewQuestion | None
) -> InterviewRead:
    total = len(interview.questions)
    notes = []
    if total < interview.requested_question_count:
        notes.append(
            f"Only {total} matching question(s) were available "
            f"(requested {interview.requested_question_count})."
        )

    return InterviewRead(
        id=interview.id,
        application_id=interview.application_id,
        status=interview.status,
        evaluation_status=interview.evaluation_status,
        end_reason=interview.end_reason,
        source=interview.source,
        experience_category=interview.experience_category,
        subjects=interview.subjects,
        difficulties=interview.difficulties,
        requested_question_count=interview.requested_question_count,
        duration_minutes=interview.duration_minutes,
        started_at=interview.started_at,
        ends_at=interview.ends_at,
        finished_at=interview.finished_at,
        remaining_seconds=remaining_seconds(interview),
        progress=build_progress(interview),
        notes=notes,
        current_question=question_out(current, total) if current else None,
    )