import pytest

from kindle_to_anki.db_reader import WordRecord, SourceBook
from kindle_to_anki.prompt_building import separate_words_by_language, get_batches

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

    with pytest.raises(ValueError):
        get_batches(german_words, 0)
    with pytest.raises(ValueError):
        get_batches(german_words, -1)

def test_make_word_block(words_by_language: dict[str, list[WordRecord]]) -> None:
    german_words = words_by_language["de"]

