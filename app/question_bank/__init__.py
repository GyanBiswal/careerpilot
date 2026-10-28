"""Validate the question banks from the terminal:  python -m app.question_bank"""
import sys

from app.question_bank.loader import load_question_banks, resolve_directory


def main() -> int:
    store = load_question_banks(resolve_directory())

    print(f"Directory: {store.directory}")
    print(f"Files found: {len(store.files)}")
    for info in store.files:
        print(
            f"  {info.file}: subject={info.subject} "
            f"valid={info.valid_questions} rejected={info.rejected_questions}"
        )

    if store.issues:
        print("\nIssues:")
        for issue in store.issues:
            where = f"{issue.file or '-'} {issue.location or ''}".strip()
            print(f"  [{issue.severity.upper()}] {where}: {issue.message}")

    print(
        f"\nLoaded {len(store.questions)} valid questions "
        f"({store.error_count} errors, {store.warning_count} warnings)."
    )
    return 1 if store.error_count else 0


if __name__ == "__main__":
    sys.exit(main())