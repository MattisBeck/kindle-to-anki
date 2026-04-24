from sqlite3 import Connection
from typing import Any, Generator
import pytest
import sqlite3
from pathlib import Path

from kindle_to_anki.db_reader import extract_information, get_cache_set, write_set_to_cache
from kindle_to_anki.db_reader import WordRecord

@pytest.fixture
def db() -> Generator[Connection, Any, None]:
    sql_location = Path(__file__).parent / "data" / "mock_vocab.sql"
    connection = sqlite3.connect(":memory:")
    with sql_location.open() as f:
        connection.executescript(f.read())

    yield connection

    connection.close()

@pytest.fixture
def cache() -> Generator[Path, Any, None]:
    cache_location = Path(__file__).parent / "data" / "cache.json"
    cache_location.write_text("[]")

    yield cache_location

    cache_location.unlink()


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

    # Test for no duplicates; all entries should already be in the cache.
    word_list = extract_information(db, cache)
    assert len(word_list) == 0