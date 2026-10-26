from app.chunking import split_transcript


def test_empty_returns_no_chunks():
    assert split_transcript("", 800) == []
    assert split_transcript("   \n\n  ", 800) == []


def test_short_text_is_single_chunk():
    assert split_transcript("Hello there friend.", 800) == ["Hello there friend."]


def test_two_small_paragraphs_pack_into_one_chunk():
    text = "one two three.\n\nfour five six."
    # max_words 800 -> both paragraphs fit in one chunk
    assert split_transcript(text, 800) == ["one two three.\n\nfour five six."]


def test_paragraphs_split_when_over_limit():
    text = "a a a.\n\nb b b.\n\nc c c."  # 3 paragraphs, 3 words each
    chunks = split_transcript(text, 4)  # only ~1 paragraph fits per chunk
    assert len(chunks) == 3
    assert chunks == ["a a a.", "b b b.", "c c c."]


def test_big_paragraph_splits_on_sentences():
    text = "one two three four. five six seven eight."  # 8 words, two sentences
    chunks = split_transcript(text, 5)
    assert chunks == ["one two three four.", "five six seven eight."]


def test_single_oversized_sentence_is_its_own_chunk():
    text = "word " * 10  # 10 words, one sentence, no terminal punctuation
    chunks = split_transcript(text.strip(), 3)
    assert len(chunks) == 1
    assert chunks[0].split() == ["word"] * 10
