"""Turn a file into text, deciding its type from its bytes.

Used by every connector that brings files (uploads now, Google Drive
next). The type comes from the content, never from the file name, and
every parser has limits, so a crafted file cannot exhaust the worker.
"""

import io
import zipfile

from pypdf import PdfReader
from pypdf.errors import PdfReadError


MAX_FILE_BYTES = 20 * 1024 * 1024
MAX_UNZIPPED_BYTES = 100 * 1024 * 1024
MAX_PDF_PAGES = 2000

SUPPORTED_TYPES = {
    "application/pdf": "PDF",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": "Word",
    "text/plain": "text",
}


class ExtractionError(ValueError):
    """The file cannot be read as text (unsupported, damaged, no text)."""


def detect_type(data: bytes) -> str:
    """The MIME type of a supported file, from its first bytes."""
    if data.startswith(b"%PDF-"):
        return "application/pdf"

    if data.startswith(b"PK\x03\x04"):
        try:
            with zipfile.ZipFile(io.BytesIO(data)) as archive:
                names = set(archive.namelist())
        except zipfile.BadZipFile:
            raise ExtractionError("damaged archive") from None
        if "word/document.xml" in names and "[Content_Types].xml" in names:
            return (
                "application/vnd.openxmlformats-officedocument."
                "wordprocessingml.document"
            )
        raise ExtractionError("unsupported archive (only Word .docx)")

    if b"\x00" not in data[:8192]:
        try:
            data.decode("utf-8")
            return "text/plain"
        except UnicodeDecodeError:
            pass

    raise ExtractionError("unsupported file type (PDF, Word .docx or text)")


def _pdf_text(data: bytes) -> str:
    try:
        reader = PdfReader(io.BytesIO(data))
        if reader.is_encrypted:
            raise ExtractionError("the PDF is password protected")
        if len(reader.pages) > MAX_PDF_PAGES:
            raise ExtractionError(f"more than {MAX_PDF_PAGES} pages")
        return "\n\n".join(page.extract_text() or "" for page in reader.pages)
    except (PdfReadError, ValueError, KeyError) as exc:
        if isinstance(exc, ExtractionError):
            raise
        raise ExtractionError(f"damaged PDF: {type(exc).__name__}") from None


def _docx_text(data: bytes) -> str:
    # A .docx is a zip: refuse archives that expand far beyond their size
    # ("zip bombs") before any parser opens them.
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        unzipped = sum(info.file_size for info in archive.infolist())
    if unzipped > MAX_UNZIPPED_BYTES:
        raise ExtractionError("the document expands to more than 100 MB")

    from docx import Document as WordDocument

    try:
        document = WordDocument(io.BytesIO(data))
    except Exception as exc:
        raise ExtractionError(f"damaged Word file: {type(exc).__name__}") from None

    parts = [paragraph.text for paragraph in document.paragraphs]
    for table in document.tables:
        for row in table.rows:
            parts.append("\t".join(cell.text for cell in row.cells))
    return "\n".join(parts)


def extract_text(data: bytes) -> tuple[str, str]:
    """Return (mime_type, text). Raises ExtractionError."""
    if len(data) > MAX_FILE_BYTES:
        raise ExtractionError("the file is larger than 20 MB")
    if not data:
        raise ExtractionError("the file is empty")

    mime_type = detect_type(data)

    if mime_type == "application/pdf":
        text = _pdf_text(data)
    elif mime_type == "text/plain":
        text = data.decode("utf-8")
    else:
        text = _docx_text(data)

    if not text.strip():
        raise ExtractionError(
            "no text found (a scanned document? text recognition comes "
            "later)"
        )

    return mime_type, text
