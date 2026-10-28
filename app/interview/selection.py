"""Pick interview questions with plain Python. No LLM involved."""
import random
from collections.abc import Sequence

from app.question_bank.models import StoredQuestion

# Essential (P1) questions are more likely to be chosen than P3 ones.
PRIORITY_WEIGHT = {"P1": 3.0, "P2": 2.0, "P3": 1.0}


def _weighted_sample(
    questions: Sequence[StoredQuestion], k: int, rng: random.Random
) -> list[StoredQuestion]:
    """Weighted random sample without replacement (Efraimidis-Spirakis)."""
    keyed = [
        (rng.random() ** (1.0 / PRIORITY_WEIGHT[q.priority]), q) for q in questions
    ]
    keyed.sort(key=lambda pair: pair[0], reverse=True)
    return [q for _, q in keyed[:k]]


def select_interview_questions(
    pool: Sequence[StoredQuestion],
    count: int,
    *,
    previously_asked_ids: set[str],
    rng: random.Random | None = None,
) -> list[StoredQuestion]:
    """Choose up to `count` distinct questions, preferring ones not asked before."""
    rng = rng or random.Random()

    fresh = [q for q in pool if q.id not in previously_asked_ids]
    seen = [q for q in pool if q.id in previously_asked_ids]

    chosen = _weighted_sample(fresh, count, rng)
    if len(chosen) < count:
        chosen += _weighted_sample(seen, count - len(chosen), rng)

    rng.shuffle(chosen)  # mix difficulties and topics into a natural order
    return chosen