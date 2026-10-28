"""Discover, validate and load question-bank JSON files.

Nothing here knows which subjects exist. Any *.json file placed in the
question bank directory is picked up automatically.
"""
import json
import logging
import threading
from pathlib import Path

from pydantic import ValidationError

from app.core.config import get_settings
from app.question_bank.models import (
    BankFileInfo,
    LoadIssue,
    Question,
    QuestionBankStore,
    StoredQuestion,
    normalize_subject,
)

logger = logging.getLogger("careerpilot.question_bank")

PROJECT_ROOT = Path(__file__).resolve().parents[2]
MAX_BANK_FILE_BYTES = 5 * 1024 * 1024


def resolve_directory() -> Path:
    configured = Path(get_settings().question_bank_dir)
    return configured if configured.is_absolute() else PROJECT_ROOT / configured


def _display_path(directory: Path) -> str:
    try:
        return str(directory.resolve().relative_to(PROJECT_ROOT))
    except ValueError:
        return directory.name


def _format_validation_error(exc: ValidationError) -> str:
    parts = []
    for error in exc.errors():
        location = ".".join(str(p) for p in error["loc"]) or "(question)"
        parts.append(f"{location}: {error['msg']}")
    return "; ".join(parts)


class _BankLoader:
    def __init__(self, directory: Path):
        self.directory = directory
        self.store = QuestionBankStore(directory=_display_path(directory))
        self._text_owner: dict[str, str] = {}

    def _issue(
        self, severity: str, file: str | None, location: str | None, message: str
    ) -> None:
        self.store.issues.append(LoadIssue(severity, file, location, message))

    def run(self) -> QuestionBankStore:
        if not self.directory.is_dir():
            self._issue(
                "warning", None, None,
                "Question bank directory not found; no questions were loaded.",
            )
            return self.store

        root = self.directory.resolve()
        for path in sorted(self.directory.glob("*.json")):
            self._load_file(path, root)

        if not self.store.files and not self.store.issues:
            self._issue("warning", None, None, "No .json question bank files found.")
        return self.store

    def _load_file(self, path: Path, root: Path) -> None:
        name = path.name

        # Never follow a symlink out of the question bank directory.
        resolved = path.resolve()
        try:
            resolved.relative_to(root)
        except ValueError:
            self._issue("error", name, None, "File resolves outside the question bank directory; skipped.")
            return
        if not resolved.is_file():
            self._issue("error", name, None, "Not a regular file; skipped.")
            return
        if resolved.stat().st_size > MAX_BANK_FILE_BYTES:
            self._issue("error", name, None, "File is larger than 5 MB; skipped.")
            return

        try:
            raw = resolved.read_text(encoding="utf-8-sig")
        except UnicodeDecodeError:
            self._issue("error", name, None, "File is not valid UTF-8; skipped.")
            return
        except OSError:
            self._issue("error", name, None, "File could not be read; skipped.")
            return

        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            self._issue(
                "error", name, None,
                f"Invalid JSON at line {exc.lineno}, column {exc.colno}: {exc.msg}",
            )
            return

        subject = normalize_subject(path.stem)
        if isinstance(data, list):
            items = data
        elif isinstance(data, dict):
            items = data.get("questions")
            if not isinstance(items, list):
                self._issue(
                    "error", name, None,
                    "Expected a JSON array of questions, or an object with a 'questions' array.",
                )
                return
            declared = data.get("subject")
            if declared is not None:
                if isinstance(declared, str) and normalize_subject(declared):
                    subject = normalize_subject(declared)
                else:
                    self._issue(
                        "error", name, None,
                        "'subject' must be a non-empty string; using the filename instead.",
                    )
        else:
            self._issue(
                "error", name, None,
                "Expected a JSON array of questions, or an object with a 'questions' array.",
            )
            return

        if not subject:
            self._issue("error", name, None, "Could not derive a subject name from the filename; skipped.")
            return
        if not items:
            self._issue("warning", name, None, "File contains no questions.")

        valid = rejected = 0
        for index, item in enumerate(items, start=1):
            label = f"question #{index}"
            if isinstance(item, dict) and isinstance(item.get("id"), str):
                label += f" (id={item['id']})"

            if not isinstance(item, dict):
                self._issue("error", name, label, "Each question must be a JSON object.")
                rejected += 1
                continue

            try:
                question = Question.model_validate(item)
            except ValidationError as exc:
                self._issue("error", name, label, _format_validation_error(exc))
                rejected += 1
                continue

            existing = self.store.by_id.get(question.id)
            if existing is not None:
                self._issue(
                    "error", name, label,
                    f"Duplicate id '{question.id}' (already defined in {existing.source_file}); "
                    "this copy was skipped.",
                )
                rejected += 1
                continue

            stored = StoredQuestion(
                **question.model_dump(), subject=subject, source_file=name
            )
            self.store.questions.append(stored)
            self.store.by_id[stored.id] = stored
            valid += 1

            text_key = " ".join(question.question.lower().split())
            owner = self._text_owner.setdefault(text_key, question.id)
            if owner != question.id:
                self._issue(
                    "warning", name, label,
                    f"Same question text as '{owner}'.",
                )

        self.store.files.append(BankFileInfo(name, subject, valid, rejected))


def load_question_banks(directory: Path) -> QuestionBankStore:
    """Load and validate every *.json file in the directory."""
    return _BankLoader(directory).run()


# ---- Shared in-memory store ----

_store: QuestionBankStore | None = None
_lock = threading.Lock()


def _log_summary(store: QuestionBankStore) -> None:
    logger.info(
        "Question banks loaded: %d questions from %d files (%d errors, %d warnings)",
        len(store.questions),
        len(store.files),
        store.error_count,
        store.warning_count,
    )
    for issue in store.issues:
        log = logger.error if issue.severity == "error" else logger.warning
        log("Question bank issue: %s %s: %s", issue.file or "-", issue.location or "", issue.message)


def reload_store() -> QuestionBankStore:
    """Rescan the directory and replace the in-memory store."""
    global _store
    with _lock:
        store = load_question_banks(resolve_directory())
        _log_summary(store)
        _store = store  # swapped in one step, so readers never see a half-built store
        return store


def get_store() -> QuestionBankStore:
    if _store is None:
        return reload_store()
    return _store