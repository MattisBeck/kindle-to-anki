import json
import sqlite3
import re
from pathlib import Path
from dataclasses import dataclass


@dataclass(frozen=True)
class WordRecord:
    word: str
    lang: str
    stem: str
    context: str
    origin: SourceBook

@dataclass(frozen=True)
class SourceBook:
    title: str
    authors: str

def extract_information(connection: sqlite3.Connection, cache_location: Path) -> list[WordRecord]:
    cache = get_cache_set(cache_location)
    cursor = connection.cursor()
    sql_query= """
        SELECT WORDS.word, WORDS.stem, WORDS.lang, LOOKUPS.usage, BOOK_INFO.authors, BOOK_INFO.title, BOOK_INFO.id, MIN(LOOKUPS.timestamp)
        FROM LOOKUPS 
        JOIN WORDS ON LOOKUPS.word_key = WORDS.id
        JOIN BOOK_INFO ON LOOKUPS.book_key = BOOK_INFO.id
        GROUP BY WORDS.stem;
    """
    res = cursor.execute(sql_query)

    words = []
    books = {}
    for word, stem, lang, context, authors, title, book_id, _ in res:
        stem = normalize_stem(stem)
        if f"{lang}:{stem}" in cache:
            continue
        if book_id not in books:
            books[book_id] = SourceBook(title, authors)
        context = context.replace("\n", " ")
        new_word = WordRecord(word, lang, stem, context, books[book_id])
        words.append(new_word)
        #FIXME Cache managment
        cache.add(f"{lang}:{stem}")

    write_set_to_cache(cache, cache_location)
    return words

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

def normalize_stem(stem: str) -> str:
    return re.sub(r" \(\d+\)$", "", stem)