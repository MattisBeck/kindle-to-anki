import sqlite3
from pathlib import Path
from kindle_to_anki.db_reader import add_words_to_cache, extract_information, get_cache_set, write_set_to_cache
from kindle_to_anki.models import SourceBook, WordRecord


def test_get_cache_set(cache: Path) -> None:
    test_data = '["Hello", "World"]'
    cache.write_text(test_data)
    assert get_cache_set(cache) == {"Hello", "World"}

def test_cache_set_create_new_file(cache: Path) -> None:
    #Delete cache
    cache.unlink()
    assert get_cache_set(cache) == set()

def test_write_set_to_cache(cache: Path) -> None:
    test_data = {"Hello", "World"}
    write_set_to_cache(test_data, cache)
    assert get_cache_set(cache) == test_data

def test_extract_information(db: sqlite3.Connection, cache: Path) -> None:
    word_list = extract_information(db, cache)

    # check for correct length
    assert len(word_list) == 10

    # check for correct type
    assert all(isinstance(word, WordRecord) for word in word_list)

    # check attributes of first word
    first_word = word_list[0]
    assert first_word.word == "Bug"
    assert first_word.stem == "Bug"
    assert first_word.lang == "de"

    # Exactly three SourceBooks need to exist.
    books = {word.origin for word in word_list}
    assert len(books) == 3

    # Reading the database should not mark words as processed.
    assert get_cache_set(cache) == set()

def test_extract_information_skips_cached_words(db: sqlite3.Connection, cache: Path) -> None:
    write_set_to_cache({"de:Bug", "en:cloud"}, cache)

    word_list = extract_information(db, cache)

    assert len(word_list) == 8
    assert all(not (word.lang == "de" and word.stem == "Bug") for word in word_list)
    assert all(not (word.lang == "en" and word.stem == "cloud") for word in word_list)

def test_add_words_to_cache(cache: Path) -> None:
    book = SourceBook("Book", "Author")
    word_list = [
        WordRecord("Bug", "de", "Bug", "Context", book),
        WordRecord("clouds", "en", "cloud", "Context", book),
    ]

    add_words_to_cache(word_list, cache)

    assert get_cache_set(cache) == {"de:Bug", "en:cloud"}
