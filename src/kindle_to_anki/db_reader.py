"""Read Kindle vocabulary records and maintain the processed-word cache."""

import json
import sqlite3
import re
from pathlib import Path
from kindle_to_anki.models import SourceBook, WordRecord

def extract_information(connection: sqlite3.Connection, cache_location: Path) -> list[WordRecord]:
    """Extract uncached vocabulary records from a Kindle vocab.db connection."""
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
        if get_cache_key(lang, stem) in cache:
            continue
        if book_id not in books:
            books[book_id] = SourceBook(title, authors)
        context = context.replace("\n", " ")
        new_word = WordRecord(word, lang, stem, context, books[book_id])
        words.append(new_word)

    return words

def get_cache_key(language_code: str, stem: str) -> str:
    """Build the stable cache key for one normalized word stem."""
    return f"{language_code}:{stem}"

def add_words_to_cache(words: list[WordRecord], cache_location: Path) -> None:
    """Persist word stems as processed in the cache file."""
    cache = get_cache_set(cache_location)
    for word in words:
        cache.add(get_cache_key(word.lang, word.stem))
    write_set_to_cache(cache, cache_location)

def get_cache_set(cache_location: Path) -> set:
    """Load the processed-word cache, creating an empty cache file when needed."""
    parent_directory = cache_location.parent
    # Create Folder & File, if it does not exist
    parent_directory.mkdir(parents=True, exist_ok=True)
    if not cache_location.is_file():
        cache_location.write_text("[]")
    with cache_location.open("r", encoding="utf-8") as file:
        cache = json.load(file)
    return set(cache)

def write_set_to_cache(cache_set: set, cache_location: Path) -> None:
    """Write the processed-word cache set as JSON."""
    with cache_location.open("w", encoding="utf-8") as file:
        json.dump(list(cache_set), file, indent=4)

def normalize_stem(stem: str) -> str:
    """Remove Kindle's numeric duplicate suffix from a stem."""
    return re.sub(r" \(\d+\)$", "", stem)
