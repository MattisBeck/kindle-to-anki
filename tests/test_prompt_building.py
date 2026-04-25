import pytest
from kindle_to_anki.db_reader import WordRecord, SourceBook
from kindle_to_anki.prompt_building import separate_words_by_language

def test_separate_words_by_language(word_list) -> None:
    separated_words = separate_words_by_language(word_list)
    assert len(separated_words.keys()) == 2
    assert len(separated_words["en"]) == 5
    assert len(separated_words["de"]) == 5