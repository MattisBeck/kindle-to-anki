import json
import sqlite3
from pathlib import Path
from dataclasses import dataclass


@dataclass
class WordRecord:
    word: str
    language: str
    stem: str
    context: str
    origin: SourceBook

    def __eq__(self, other):
        return self.word == other.word and self.language == other.language

@dataclass
class SourceBook:
    title: str
    author: str

def extract_information(connection: sqlite3.Connection, cache_location: Path) -> list[WordRecord]:
    cache = get_cache_set(cache_location)

    cursor = connection.cursor()
    cursor.execute("""
        SELECT WORDS.word, WORDS.stem, WORDS.lang, LOOKUPS.usage, BOOK_INFO.authors, BOOK_INFO.title
        FROM LOOKUPS 
        JOIN WORDS ON LOOKUPS.word_key = WORDS.id
        JOIN BOOK_INFO ON LOOKUPS.book_key = BOOK_INFO.id;;
    """)

    write_set_to_cache(cache, cache_location)

def get_cache_set(cache_location: Path) -> set:
    parent_directory = cache_location.parent
    # Create Folder & File, if it does not exist
    parent_directory.mkdir(parents=True, exist_ok=True)
    if not cache_location.is_file():
        cache_location.write_text("[]")
    with cache_location.open("r", encoding="utf-8") as file:
        cache = json.load(file)
    return set(cache)

def write_set_to_cache(cache_set: set, cache_location: Path) -> None:
    with cache_location.open("w", encoding="utf-8") as file:
        json.dump(list(cache_set), file, indent=4)