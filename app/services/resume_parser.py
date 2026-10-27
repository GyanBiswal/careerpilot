"""Validate an uploaded resume and extract its text.

Everything here works on bytes in memory. Nothing is written to disk, and the
user-supplied filename is never used to build a path.
"""
import io
import logging
import os
import re
import zipfile
from dataclasses import dataclass

import pymupdf
from docx import Document
from docx.table import Table
from docx.text.paragraph import Paragraph

logger = logging.getLogger("careerpilot.resume_parser")

ALLOWED_EXTENSIONS = {".pdf": "pdf", ".docx": "docx"}
MAX_DOCX_UNCOMPRESSED_BYTES = 50 * 1024 * 1024  # zip-bomb guard
MAX_TEXT_CHARS = 100_000


class ResumeFileError(Exception):
    """A problem with the uploaded file, safe to show to the user."""

    def __init__(self, message: str, status_code: int = 422):
        super().__init__(message)
        self.message = message
        self.status_code = status_code


@dataclass
class ParsedResume:
    text: str
    file_type: str  # "pdf" or "docx"
    page_count: int | None  # None for DOCX (pages aren't defined in the file)


def sanitize_filename(name: str) -> str:
    """Make a filename safe to store and display (never used as a path)."""
    name = os.path.basename(name.replace("\\", "/"))
    name = re.sub(r"[^\w.\- ]", "_", name).strip()
    return name[:255] or "resume"


def detect_file_type(filename: str, data: bytes) -> str:
    """Check the extension AND the file's real signature."""
    extension = os.path.splitext(filename.lower())[1]
    file_type = ALLOWED_EXTENSIONS.get(extension)
    if file_type is None:
        raise ResumeFileError(
            "Unsupported file type. Only PDF and DOCX files are allowed.", 415
        )

    if file_type == "pdf":
        matches = data.startswith(b"%PDF-")
    else:
        matches = data.startswith(b"PK\x03\x04")  # DOCX is a ZIP archive
    if not matches:
        raise ResumeFileError("File content does not match its extension.", 415)
    return file_type


def _normalize_text(text: str) -> str:
    # PostgreSQL cannot store NUL characters, and some PDFs contain them.
    text = text.replace("\x00", "")
    lines = [re.sub(r"[ \t]+", " ", line).strip() for line in text.splitlines()]
    text = "\n".join(lines)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def _extract_pdf(data: bytes, max_pages: int) -> tuple[str, int]:
    with pymupdf.open(stream=data, filetype="pdf") as doc:
        if doc.needs_pass:
            raise ResumeFileError("Password-protected PDFs are not supported.")
        if doc.page_count > max_pages:
            raise ResumeFileError(
                f"PDF has too many pages (maximum is {max_pages})."
            )
        pages = [page.get_text("text") for page in doc]
        return "\n\n".join(pages), doc.page_count


def _extract_docx(data: bytes) -> str:
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            if "word/document.xml" not in archive.namelist():
                raise ResumeFileError("File is not a valid DOCX document.")
            total_size = sum(info.file_size for info in archive.infolist())
            if total_size > MAX_DOCX_UNCOMPRESSED_BYTES:
                raise ResumeFileError("DOCX file is too large once unpacked.")
    except zipfile.BadZipFile:
        raise ResumeFileError("File is corrupted or not a valid DOCX document.")

    document = Document(io.BytesIO(data))
    parts: list[str] = []
    # iter_inner_content keeps paragraphs and tables in their document order.
    for block in document.iter_inner_content():
        if isinstance(block, Paragraph):
            parts.append(block.text)
        elif isinstance(block, Table):
            for row in block.rows:
                # dict.fromkeys drops the repeats that merged cells produce.
                cells = list(dict.fromkeys(c.text.strip() for c in row.cells))
                parts.append(" | ".join(c for c in cells if c))
    return "\n".join(parts)


def parse_resume(filename: str, data: bytes, max_pages: int) -> ParsedResume:
    file_type = detect_file_type(filename, data)

    try:
        if file_type == "pdf":
            raw_text, page_count = _extract_pdf(data, max_pages)
        else:
            raw_text, page_count = _extract_docx(data), None
    except ResumeFileError:
        raise
    except Exception:
        # Third-party parsers raise many different exception types on bad input.
        logger.exception("Failed to parse uploaded %s file", file_type)
        raise ResumeFileError("Could not read this file. It may be corrupted.")

    text = _normalize_text(raw_text)
    if not text:
        raise ResumeFileError(
            "No text could be extracted. Scanned or image-only files are not supported."
        )
    if len(text) > MAX_TEXT_CHARS:
        raise ResumeFileError("The resume text is too long to process.")

    return ParsedResume(text=text, file_type=file_type, page_count=page_count)