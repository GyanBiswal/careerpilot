"""Pure-Python filtering of loaded questions. No LLM involved."""
from collections.abc import Iterable

from app.question_bank.models import StoredQuestion, normalize_subject


def _norm(value: str) -> str:
    return " ".join(value.lower().split())


def _set(values: Iterable[str] | None, normalizer) -> set[str] | None:
    return {normalizer(v) for v in values} if values else None


def filter_questions(
    questions: Iterable[StoredQuestion],
    *,
    subjects: list[str] | None = None,
    topics: list[str] | None = None,
    subtopics: list[str] | None = None,
    difficulties: list[str] | None = None,
    experience_category: str | None = None,
    roles: list[str] | None = None,
    priorities: list[str] | None = None,
) -> list[StoredQuestion]:
    """Keep questions matching ALL given filters.

    Within one filter, any value may match (OR): difficulty=easy&difficulty=medium
    returns both. Text comparisons ignore case and extra whitespace.
    """
    subject_set = _set(subjects, normalize_subject)
    topic_set = _set(topics, _norm)
    subtopic_set = _set(subtopics, _norm)
    difficulty_set = set(difficulties) if difficulties else None
    priority_set = set(priorities) if priorities else None
    role_set = _set(roles, _norm)

    result = []
    for q in questions:
        if subject_set and q.subject not in subject_set:
            continue
        if topic_set and _norm(q.topic) not in topic_set:
            continue
        if subtopic_set and _norm(q.subtopic) not in subtopic_set:
            continue
        if difficulty_set and q.difficulty not in difficulty_set:
            continue
        if priority_set and q.priority not in priority_set:
            continue
        if experience_category and q.experience_category != experience_category:
            continue
        if role_set and not role_set.intersection(_norm(r) for r in q.role_tags):
            continue
        result.append(q)
    return result