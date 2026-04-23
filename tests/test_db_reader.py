from sqlite3 import Connection
from typing import Any, Generator

import pytest
import sqlite3
from pathlib import Path

from kindle_to_anki.db_reader import extract_information, get_cache_set, write_set_to_cache

@pytest.fixture
def db() -> Generator[Connection, Any, None]:
    connection = sqlite3.connect(":memory:")
    with open("data/mock_vocab.sql", "r") as f:
        connection.executescript(f.read())

    yield connection

    connection.close()

@pytest.fixture
def cache() -> Generator[Path, Any, None]:
    cache_location = Path("data/cache.json")
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