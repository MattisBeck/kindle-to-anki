import pytest

from kindle_to_anki.models import SourceBook, WordRecord, PromptType
from kindle_to_anki.prompt_building import (
    get_batches,
    make_word_block,
    separate_words_by_language,
    get_language,
    batch_to_prompt,
    get_all_prompts
)

def test_separate_words_by_language(word_list: list[WordRecord]) -> None:
    separated_words = separate_words_by_language(word_list)
    assert len(separated_words.keys()) == 2
    assert len(separated_words["en"]) == 5
    assert len(separated_words["de"]) == 5

def test_separate_words_by_language_empty_input() -> None:
    separated_words = separate_words_by_language([])
    assert len(separated_words) == 0

def test_get_batches(words_by_language: dict[str, list[WordRecord]]) -> None:
    german_words = words_by_language["de"]
    batches = get_batches(german_words, 2)
    assert len(batches) == 3
    assert len(batches[0]) == 2 and len(batches[1]) == 2 and len(batches[2]) == 1

    batches = get_batches(german_words, 1)
    assert len(batches) == 5

    batches = get_batches(german_words, 10)
    assert len(batches) == 1

    assert get_batches([], 2) == []


    with pytest.raises(ValueError):
        get_batches(german_words, 0)
    with pytest.raises(ValueError):
        get_batches(german_words, -1)

def test_make_word_block() -> None:
    book_a = SourceBook("Book A", "Author A")
    book_b = SourceBook("Book B", "Author B")
    batch = [
        WordRecord("alpha", "de", "alpha", "Alpha context.", book_a),
        WordRecord("beta", "de", "beta", "Beta context.", book_b),
    ]

    expected = "\n".join([
        "Book A : A",
        "Book B : B\n",

        "VOCABULARY ITEMS:\n",

        "ITEM 0",
        "word: alpha",
        "context: Alpha context.",
        "book: A\n",

        "ITEM 1",
        "word: beta",
        "context: Beta context.",
        "book: B"
    ])

    assert make_word_block(batch) == expected

def test_get_language():
    assert get_language("de") == "German"
    assert get_language("en") == "English"
    with pytest.raises(ValueError):
        get_language("Shyriiwook")

def test_batch_to_prompt(words_by_language: dict[str, list[WordRecord]]) -> None:
    native_words = words_by_language["de"]
    foreign_words = words_by_language["en"]
    native_prompt = batch_to_prompt(native_words, "de", "de")
    foreign_prompt = batch_to_prompt(foreign_words, "de", "en")

    assert "You are a language learning expert" in native_prompt
    assert "You are a language learning expert" in foreign_prompt

    assert "Native Vocabulary Definition" in native_prompt
    assert "Native Vocabulary Definition" not in foreign_prompt

    assert "Foreign Vocabulary Card Fields" not in native_prompt
    assert "Foreign Vocabulary Card Fields" in foreign_prompt
    assert "cloze_phrase" not in native_prompt
    assert "cloze_phrase" in foreign_prompt
    assert "must contain the input word exactly" in foreign_prompt

    assert "VOCABULARY ITEMS:" in native_prompt
    assert "VOCABULARY ITEMS:" in foreign_prompt

    assert "book: A" in native_prompt
    assert "book: A" in foreign_prompt

    assert native_words[0].word in native_prompt
    assert foreign_words[0].word in foreign_prompt

    with pytest.raises(ValueError):
        batch_to_prompt(native_words, "de", "xx")

def test_get_all_prompts(words_by_language: dict[str, list[WordRecord]]) -> None:
    prompts = get_all_prompts(words_by_language, "de", 2)

    assert get_all_prompts({}, "de", 2) == {}
    with pytest.raises(ValueError):
        get_all_prompts(words_by_language, "xx", 2)

    # Should also contain two languages
    assert len(prompts) == 2
    assert len(prompts["de"]) == 3 and len(prompts["en"]) == 3

    first_prompt_job = prompts["de"][0]
    assert prompts["en"][0].type == PromptType.FOREIGN_VOCABULARY
    assert first_prompt_job.type == PromptType.NATIVE_DEFINITION
    assert len(first_prompt_job.words) == 2 and isinstance(first_prompt_job.words[0], WordRecord)

    # Test if order of WordRecords is preserved; Because of the batch size, the first two objects need to match
    assert first_prompt_job.words == words_by_language["de"][:2]
    assert prompts["en"][0].words == words_by_language["en"][:2]
