import sqlite3
import pytest
from typing import Any, Generator
from pathlib import Path
from kindle_to_anki.db_reader import WordRecord, extract_information
from kindle_to_anki.prompt_building import separate_words_by_language

@pytest.fixture
def db() -> Generator[sqlite3.Connection, Any, None]:
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

@pytest.fixture
def word_list(db: sqlite3.Connection, cache:Path) -> list[WordRecord]:
    return extract_information(db, cache)

@pytest.fixture
def words_by_language(word_list: list[WordRecord]) -> dict[str, list[WordRecord]]:
    return separate_words_by_language(word_list)