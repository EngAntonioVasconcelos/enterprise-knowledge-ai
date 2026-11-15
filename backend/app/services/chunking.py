"""Cut a document's normalized text into passages for retrieval.

Why cut at all: an answer usually lives in one or two paragraphs, and both
the search and the language model work better with focused passages than
with an 80-page manual.

How:
- The text is read as blocks (paragraphs, list items, headings), never
  cutting inside a sentence unless a single sentence is enormous.
- A heading starts a new passage and is remembered as its "heading", so a
  passage about holidays knows it belongs to "4.2 Holidays" even when the
  word is not repeated.
- Blocks are packed up to TARGET_CHARS; the last short block of a passage
  is repeated at the start of the next (overlap), so an idea split across
  two passages is still found whole.
- Every passage keeps its exact position: content == text[start:end].
"""

import math
import re
from dataclasses import dataclass


TARGET_CHARS = 1200
MAX_CHARS = 2000
OVERLAP_MAX_CHARS = 300

MARKDOWN_HEADING = re.compile(r"^#{1,6}\s+\S")
NUMBERED_HEADING = re.compile(r"^(\d+(\.\d+)*\.?|[IVXLC]+\.)\s+\S")
SENTENCE_END = re.compile(r"(?<=[.!?;:])\s+")


@dataclass(frozen=True)
class Chunk:
    ordinal: int
    heading: str | None
    content: str
    start_char: int
    end_char: int

    @property
    def token_estimate(self) -> int:
        # About four characters per token for European languages.
        return max(1, math.ceil(len(self.content) / 4))


@dataclass(frozen=True)
class _Block:
    start: int
    end: int
    is_heading: bool


def _looks_like_heading(line: str) -> bool:
    line = line.strip()
    if not line or len(line) > 90:
        return False
    if MARKDOWN_HEADING.match(line):
        return True
    if line.endswith((".", ",", ";", ":")) and not NUMBERED_HEADING.match(line):
        return False
    if NUMBERED_HEADING.match(line) and len(line.split()) <= 12:
        return True
    letters = [c for c in line if c.isalpha()]
    return len(letters) >= 4 and all(c.isupper() for c in letters) and len(line.split()) <= 10


def _blocks(text: str) -> list[_Block]:
    """Non-empty lines grouped into paragraphs, headings on their own."""
    blocks: list[_Block] = []
    start = None
    end = 0
    position = 0
    for line in text.split("\n"):
        line_start, line_end = position, position + len(line)
        position = line_end + 1
        stripped = line.strip()
        if not stripped:
            if start is not None:
                blocks.append(_Block(start, end, False))
                start = None
            continue
        first = line_start + (len(line) - len(line.lstrip()))
        last = line_end - (len(line) - len(line.rstrip()))
        if _looks_like_heading(line):
            if start is not None:
                blocks.append(_Block(start, end, False))
                start = None
            blocks.append(_Block(first, last, True))
            continue
        if start is None:
            start = first
        end = last
    if start is not None:
        blocks.append(_Block(start, end, False))
    return blocks


def _split_long(text: str, block: _Block) -> list[_Block]:
    """A block larger than MAX_CHARS, cut at sentence ends (or hard)."""
    pieces: list[_Block] = []
    start = block.start
    while block.end - start > MAX_CHARS:
        window = text[start:start + MAX_CHARS]
        cut = None
        for match in SENTENCE_END.finditer(window):
            if match.start() >= TARGET_CHARS // 2:
                cut = match.start()
        if cut is None:
            space = window.rfind(" ", TARGET_CHARS // 2)
            cut = space if space > 0 else MAX_CHARS
        pieces.append(_Block(start, start + cut, False))
        start += cut
        while start < block.end and text[start].isspace():
            start += 1
    if start < block.end:
        pieces.append(_Block(start, block.end, False))
    return pieces


def _heading_text(text: str, block: _Block) -> str:
    return text[block.start:block.end].lstrip("#").strip()[:300]


def chunk_text(text: str) -> list[Chunk]:
    chunks: list[Chunk] = []
    heading: str | None = None
    current: list[_Block] = []

    def emit() -> None:
        if not current:
            return
        start, end = current[0].start, current[-1].end
        chunks.append(
            Chunk(
                ordinal=len(chunks),
                heading=heading,
                content=text[start:end],
                start_char=start,
                end_char=end,
            )
        )

    for block in _blocks(text):
        if block.is_heading:
            emit()
            current = []
            heading = _heading_text(text, block)
            # The heading itself is searchable with its section.
            current = [block]
            continue
        for piece in _split_long(text, block):
            size = piece.end - (current[0].start if current else piece.start)
            if current and size > TARGET_CHARS and not (
                len(current) == 1 and current[0].is_heading
            ):
                emit()
                last = current[-1]
                overlap = (
                    not last.is_heading
                    and last.end - last.start <= OVERLAP_MAX_CHARS
                    and piece.end - last.start <= MAX_CHARS
                )
                current = [last] if overlap else []
            current.append(piece)
    emit()
    return chunks
