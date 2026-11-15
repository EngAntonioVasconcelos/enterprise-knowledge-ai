import io
import zipfile

import pytest
from docx import Document as WordDocument

from app.services import text_extraction
from app.services.text_extraction import (
    ExtractionError,
    detect_type,
    extract_text,
)


WORD = (
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
)


def make_pdf(text: str) -> bytes:
    """A minimal one-page PDF with a line of text (no extra libraries)."""
    stream = f"BT /F1 12 Tf 72 720 Td ({text}) Tj ET".encode("latin-1")
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
        b"/Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>",
        b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n"
        + stream + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    out = io.BytesIO()
    out.write(b"%PDF-1.4\n")
    offsets = []
    for number, body in enumerate(objects, start=1):
        offsets.append(out.tell())
        out.write(f"{number} 0 obj\n".encode() + body + b"\nendobj\n")
    xref = out.tell()
    out.write(f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode())
    for offset in offsets:
        out.write(f"{offset:010d} 00000 n \n".encode())
    out.write(
        f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\n"
        f"startxref\n{xref}\n%%EOF\n".encode()
    )
    return out.getvalue()


def make_docx(paragraphs, table=None) -> bytes:
    document = WordDocument()
    for paragraph in paragraphs:
        document.add_paragraph(paragraph)
    if table:
        grid = document.add_table(rows=len(table), cols=len(table[0]))
        for r, row in enumerate(table):
            for c, value in enumerate(row):
                grid.cell(r, c).text = value
    out = io.BytesIO()
    document.save(out)
    return out.getvalue()


def test_pdf_text_is_extracted():
    mime, text = extract_text(make_pdf("Employees get 22 days of vacation"))

    assert mime == "application/pdf"
    assert "22 days of vacation" in text


def test_word_paragraphs_and_tables_are_extracted():
    mime, text = extract_text(
        make_docx(["Vacation policy"], table=[["Team", "Days"], ["Ops", "25"]])
    )

    assert mime == WORD
    assert "Vacation policy" in text
    assert "Ops\t25" in text


def test_plain_text_is_read_as_utf8():
    assert extract_text("F\u00e9rias: 22 dias".encode()) == (
        "text/plain",
        "F\u00e9rias: 22 dias",
    )


def test_the_type_comes_from_the_bytes_not_the_name():
    png = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32

    with pytest.raises(ExtractionError):
        detect_type(png)

    archive = io.BytesIO()
    with zipfile.ZipFile(archive, "w") as z:
        z.writestr("notes.txt", "not a word file")
    with pytest.raises(ExtractionError):
        detect_type(archive.getvalue())


def test_files_that_expand_too_much_are_refused(monkeypatch):
    monkeypatch.setattr(text_extraction, "MAX_UNZIPPED_BYTES", 1_000)
    data = make_docx(["x" * 5_000])

    with pytest.raises(ExtractionError) as error:
        extract_text(data)
    assert "expands" in str(error.value)


def test_empty_large_and_textless_files_are_refused(monkeypatch):
    with pytest.raises(ExtractionError):
        extract_text(b"")

    monkeypatch.setattr(text_extraction, "MAX_FILE_BYTES", 10)
    with pytest.raises(ExtractionError):
        extract_text(b"x" * 11)

    monkeypatch.setattr(text_extraction, "MAX_FILE_BYTES", 20 * 1024 * 1024)
    with pytest.raises(ExtractionError) as error:
        extract_text(make_pdf(""))
    assert "no text" in str(error.value)
