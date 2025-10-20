"""
Database functions for reading Kindle vocabulary database
"""

import sqlite3
import sys
from pathlib import Path
from typing import Dict, List, Tuple

from .helpers import normalize_language_code


def connect_to_db(db_path: str) -> sqlite3.Connection:
    """
    Connect to Kindle vocabulary database
    
    Args:
        db_path: Path to vocab.db file
        
    Returns:
        SQLite connection object
    """
    if not Path(db_path).exists():
        print(f"❌ Error: Database '{db_path}' not found!")
        sys.exit(1)
    return sqlite3.connect(db_path)


def get_vocabulary_data(conn: sqlite3.Connection) -> List[Dict]:
    """
    Read all vocabulary with context from database
    Combines WORDS, LOOKUPS and BOOK_INFO tables
    
    Args:
        conn: SQLite connection object
        
    Returns:
        List of vocabulary dictionaries
    """
    cursor = conn.cursor()
    
    query = """
    SELECT 
        w.id,
        w.word,
        w.lang,
        l.usage,
        b.title,
        b.authors
    FROM WORDS w
    LEFT JOIN LOOKUPS l ON w.id = l.word_key
    LEFT JOIN BOOK_INFO b ON l.book_key = b.id
    ORDER BY w.timestamp DESC
    """
    
    cursor.execute(query)
    results = cursor.fetchall()
    
    vocab_list = []
    for row in results:
        original_lang = row[2]
        vocab_list.append({
            'id': row[0],
            'word': row[1],
            'lang': original_lang,
            'lang_normalized': normalize_language_code(original_lang),
            'usage': row[3] or '',
            'book': row[4] or 'Unknown',
            'authors': row[5] or 'Unknown'
        })
    
    return vocab_list


def filter_vocabulary_by_language(vocab_list: List[Dict], language_code: str) -> List[Dict]:
    """Return vocabulary entries that match the requested language code."""
    code = language_code.lower()
    return [v for v in vocab_list if v.get('lang_normalized') == code]


def separate_by_language(vocab_list: List[Dict]) -> Tuple[List[Dict], List[Dict]]:
    """Backward compatible helper returning English and German subsets."""
    return (
        filter_vocabulary_by_language(vocab_list, 'en'),
        filter_vocabulary_by_language(vocab_list, 'de'),
    )
