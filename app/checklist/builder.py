"""Build a prep checklist from an analysis and the loaded question banks.

Everything here is deterministic Python. Same inputs, same checklist.
"""
from collections import Counter
from dataclasses import dataclass

from app.checklist.matching import AliasMap, QuestionIndex, match_strength, tokenize
from app.question_bank.models import StoredQuestion
from app.schemas.analysis import ResumeJDAnalysis
from app.schemas.checklist import ChecklistItem

PRIORITY_RANK = {"P1": 0, "P2": 1, "P3": 2}
DIFFICULTY_RANK = {"easy": 0, "medium": 1, "hard": 2}
SOURCE_RANK = {"analysis": 0, "skill_gap": 1, "general": 2}
DEFAULT_TARGETS = {"P1": 5, "P2": 3, "P3": 2}

GENERAL_TOPICS = [
    ("Behavioral", "Behavioral and HR questions come up in almost every interview."),
    (
        "Resume project discussion",
        "Interviewers usually ask you to explain and defend the projects on your resume.",
    ),
]


@dataclass
class TopicRequest:
    topic: str
    priority: str
    source: str
    reason: str


@dataclass(frozen=True)
class _Candidate:
    question: StoredQuestion
    strength: int


def derive_topics(analysis: ResumeJDAnalysis, aliases: AliasMap) -> list[TopicRequest]:
    """Turn the analysis into a de-duplicated list of topics to prepare."""
    merged: dict[frozenset[str], TopicRequest] = {}

    def add(topic: str, priority: str, source: str, reason: str) -> None:
        key = frozenset(tokenize(topic, aliases))
        if not key:
            return
        existing = merged.get(key)
        if existing is None:
            merged[key] = TopicRequest(topic.strip(), priority, source, reason.strip())
        elif PRIORITY_RANK[priority] < PRIORITY_RANK[existing.priority]:
            existing.priority = priority  # the same topic from two sources keeps the higher priority

    for item in analysis.interview_topics:
        add(item.topic, item.priority, "analysis", item.reason)

    for gap in analysis.missing_skills:
        priority = "P1" if gap.importance == "required" else "P3"
        add(gap.skill, priority, "skill_gap", gap.reason)

    for topic, reason in GENERAL_TOPICS:
        add(topic, "P2", "general", reason)

    return list(merged.values())


def _select(candidates: list[_Candidate], target: int, used_ids: set[str]) -> list[_Candidate]:
    """Pick up to `target` questions, one at a time.

    Preference order: not used by another topic, strongest match, essential (P1)
    first, then the least-represented difficulty so far, then easier first.
    """
    remaining = list(candidates)
    chosen: list[_Candidate] = []
    difficulty_counts: Counter[str] = Counter()

    while remaining and len(chosen) < target:
        best = min(
            remaining,
            key=lambda c: (
                c.question.id in used_ids,
                -c.strength,
                PRIORITY_RANK[c.question.priority],
                difficulty_counts[c.question.difficulty],
                DIFFICULTY_RANK[c.question.difficulty],
                c.question.id,
            ),
        )
        remaining.remove(best)
        chosen.append(best)
        difficulty_counts[best.question.difficulty] += 1
    return chosen


def build_checklist(
    topics: list[TopicRequest],
    questions: list[StoredQuestion],
    *,
    experience_category: str,
    difficulties: list[str] | None,
    questions_per_topic: int | None,
    aliases: AliasMap,
) -> list[ChecklistItem]:
    pool = [
        (q, QuestionIndex.build(q, aliases))
        for q in questions
        if not difficulties or q.difficulty in difficulties
    ]
    other_category = "experienced" if experience_category == "fresher" else "fresher"

    used_ids: set[str] = set()
    items: list[ChecklistItem] = []

    ordered = sorted(
        topics,
        key=lambda t: (PRIORITY_RANK[t.priority], SOURCE_RANK[t.source], t.topic.lower()),
    )
    for request in ordered:
        topic_tokens = frozenset(tokenize(request.topic, aliases))

        candidates: list[_Candidate] = []
        other_category_count = 0
        for question, index in pool:
            strength = match_strength(topic_tokens, index)
            if strength == 0:
                continue
            if question.experience_category == experience_category:
                candidates.append(_Candidate(question, strength))
            else:
                other_category_count += 1

        target = questions_per_topic or DEFAULT_TARGETS[request.priority]
        chosen = _select(candidates, target, used_ids)
        reused = any(c.question.id in used_ids for c in chosen)
        used_ids.update(c.question.id for c in chosen)

        if not chosen:
            status = "uncovered"
        elif len(chosen) < target:
            status = "partial"
        else:
            status = "covered"

        note = None
        if not chosen:
            if other_category_count:
                note = (
                    f"No {experience_category} questions match this topic; "
                    f"{other_category_count} {other_category} question(s) exist."
                )
            else:
                note = (
                    "No questions in the loaded banks match this topic. "
                    "Consider adding a question bank for it."
                )
        elif len(chosen) < target:
            note = (
                f"Only {len(candidates)} matching {experience_category} "
                f"question(s) available (target {target})."
            )
        if reused:
            extra = "Includes questions also listed under other topics."
            note = f"{note} {extra}" if note else extra

        items.append(
            ChecklistItem(
                topic=request.topic,
                priority=request.priority,
                source=request.source,
                reason=request.reason,
                status=status,
                matched_subjects=sorted({c.question.subject for c in candidates}),
                target_count=target,
                available_count=len(candidates),
                note=note,
                question_ids=[c.question.id for c in chosen],
            )
        )
    return items