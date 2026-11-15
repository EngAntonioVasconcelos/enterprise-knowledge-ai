import pytest

from app.services.chunking import MAX_CHARS, TARGET_CHARS, chunk_text


def _check_spans(text, chunks):
    for chunk in chunks:
        assert chunk.content == text[chunk.start_char:chunk.end_char]
        assert chunk.content.strip() == chunk.content
    assert [c.ordinal for c in chunks] == list(range(len(chunks)))


def test_empty_text_has_no_chunks():
    assert chunk_text("") == []
    assert chunk_text("\n\n   \n") == []


def test_a_short_text_is_one_chunk():
    text = "Just one paragraph about the office."
    [chunk] = chunk_text(text)

    assert (chunk.content, chunk.heading, chunk.start_char) == (text, None, 0)
    assert chunk.token_estimate == 9


@pytest.mark.parametrize(
    "heading",
    ["# Holidays", "## 4.2 Holidays", "4.2 Holidays", "IV. Holidays", "HOLIDAY POLICY"],
)
def test_headings_start_a_new_chunk_and_label_it(heading):
    text = f"Intro paragraph.\n\n{heading}\n\nEveryone gets 25 days.\n"
    chunks = chunk_text(text)

    _check_spans(text, chunks)
    assert [c.heading for c in chunks] == [None, heading.lstrip("#").strip()]
    assert chunks[1].content.startswith(heading)
    assert chunks[1].content.endswith("Everyone gets 25 days.")


def test_sentences_ending_with_a_period_are_not_headings():
    text = "This is a normal sentence.\nAnother one follows here.\n"
    [chunk] = chunk_text(text)

    assert chunk.heading is None


def test_paragraphs_are_packed_and_short_ones_overlap():
    paragraphs = [f"Paragraph {i}. " + "word " * 40 for i in range(12)]
    text = "\n\n".join(paragraphs)
    chunks = chunk_text(text)

    _check_spans(text, chunks)
    assert len(chunks) > 1
    assert all(len(c.content) <= MAX_CHARS for c in chunks)
    # The last paragraph of a chunk opens the next one.
    for previous, following in zip(chunks, chunks[1:]):
        last_paragraph = previous.content.split("\n\n")[-1]
        assert following.content.startswith(last_paragraph)


def test_a_huge_paragraph_is_cut_at_sentence_ends():
    sentence = "This sentence is about vacation rules and approvals. "
    text = sentence * 120
    chunks = chunk_text(text)

    _check_spans(text, chunks)
    assert len(chunks) > 2
    assert all(len(c.content) <= MAX_CHARS for c in chunks)
    assert all(c.content.endswith(".") for c in chunks[:-1])


def test_a_huge_word_without_spaces_is_still_cut():
    text = "x" * (MAX_CHARS * 2 + 10)
    chunks = chunk_text(text)

    _check_spans(text, chunks)
    assert sum(len(c.content) for c in chunks) == len(text)


def test_target_size_is_respected_roughly():
    text = "\n\n".join("Line of text number %d with some words." % i for i in range(300))
    chunks = chunk_text(text)

    assert max(len(c.content) for c in chunks) <= TARGET_CHARS + 400
