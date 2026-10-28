"""Match free-text topics (from the analysis) to question-bank metadata.

Pure Python: no LLM calls. Both sides are normalized the same way, so a topic
like "Node.js" and a bank subject like "nodejs_express" can meet.
"""
import json
import logging
import re
from dataclasses import dataclass

from app.question_bank.loader import PROJECT_ROOT
from app.question_bank.models import StoredQuestion

logger = logging.getLogger("careerpilot.checklist")

ALIASES_PATH = PROJECT_ROOT / "data" / "topic_aliases.json"

# phrase (as tokens) -> replacement (as tokens)
AliasMap = dict[tuple[str, ...], tuple[str, ...]]

# Filler words that appear in topic names but carry no subject information.
_STOP_WORDS = {
    "and", "or", "of", "the", "for", "in", "with", "to", "a", "an", "on",
    "using", "fundamental", "basic", "concept", "skill", "knowledge",
    "experience", "understanding",
}


def _stem(token: str) -> str:
    """Very simple plural handling: 'apis' -> 'api'. Applied to both sides."""
    if len(token) > 3 and token.endswith("s") and not token.endswith("ss"):
        return token[:-1]
    return token


def _raw_tokens(text: str) -> list[str]:
    # Dots are removed so "Node.js" becomes "nodejs"; + and # keep "c++" and "c#".
    cleaned = text.lower().replace(".", "")
    tokens = [_stem(t) for t in re.findall(r"[a-z0-9+#]+", cleaned)]
    return [t for t in tokens if t not in _STOP_WORDS]


def load_aliases() -> AliasMap:
    """Read data/topic_aliases.json (optional). Read fresh each time, so edits apply immediately."""
    if not ALIASES_PATH.is_file():
        return {}
    try:
        raw = json.loads(ALIASES_PATH.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        logger.error("Could not read %s; continuing without aliases", ALIASES_PATH.name)
        return {}
    if not isinstance(raw, dict):
        logger.error("%s must contain a JSON object; continuing without aliases", ALIASES_PATH.name)
        return {}

    aliases: AliasMap = {}
    for key, value in raw.items():
        if not isinstance(key, str) or not isinstance(value, str):
            logger.warning("Ignoring invalid alias entry: %r", key)
            continue
        key_tokens, value_tokens = tuple(_raw_tokens(key)), tuple(_raw_tokens(value))
        if key_tokens and value_tokens:
            aliases[key_tokens] = value_tokens
        else:
            logger.warning("Ignoring empty alias entry: %r", key)
    return aliases


def tokenize(text: str, aliases: AliasMap) -> list[str]:
    """Normalize text to tokens, replacing aliased phrases (longest match first)."""
    tokens = _raw_tokens(text)
    if not aliases:
        return tokens

    longest = max(len(key) for key in aliases)
    result: list[str] = []
    i = 0
    while i < len(tokens):
        for size in range(min(longest, len(tokens) - i), 0, -1):
            replacement = aliases.get(tuple(tokens[i : i + size]))
            if replacement is not None:
                result.extend(replacement)
                i += size
                break
        else:
            result.append(tokens[i])
            i += 1
    return result


@dataclass(frozen=True)
class QuestionIndex:
    area: frozenset[str]     # words from the subject and topic
    detail: frozenset[str]   # words from the subtopic

    @classmethod
    def build(cls, question: StoredQuestion, aliases: AliasMap) -> "QuestionIndex":
        area = tokenize(question.subject, aliases) + tokenize(question.topic, aliases)
        return cls(
            area=frozenset(area),
            detail=frozenset(tokenize(question.subtopic, aliases)),
        )


def match_strength(topic_tokens: frozenset[str], index: QuestionIndex) -> int:
    """3 = all topic words are in the subject/topic, 2 = also needs the subtopic, 0 = no match."""
    if not topic_tokens:
        return 0
    if topic_tokens <= index.area:
        return 3
    if topic_tokens <= index.area | index.detail:
        return 2
    return 0