"""
Cache management for translations and book metadata
"""

import json
import os
from pathlib import Path
from typing import Dict, Optional

from .config import build_field_key


def load_translated_cache(cache_file: str, verbose: bool = False) -> Dict:
    """
    Load translation cache from JSON file
    
    Format:
    {
        "en_words": {"lemma1": {...card...}, "lemma2": {...}},
        "de_words": {"lemma1": {...card...}, "lemma2": {...}}
    }
    
    Args:
        cache_file: Path to cache JSON file
        verbose: Enable verbose output
        
    Returns:
        Cache dictionary
    """
    cache: Dict = {
        'version': 2,
        'languages': {}
    }
    
    if os.path.exists(cache_file):
        try:
            with open(cache_file, 'r', encoding='utf-8') as f:
                loaded_cache = json.load(f)
                
                # Validate structure
                if isinstance(loaded_cache, dict):
                    if 'languages' in loaded_cache:
                        cache['languages'] = loaded_cache.get('languages', {})
                        cache['version'] = loaded_cache.get('version', 2)
                    else:
                        # Legacy schema migration (en_words/de_words)
                        migrated_languages = {}
                        en_words = loaded_cache.get('en_words', {})
                        de_words = loaded_cache.get('de_words', {})
                        if en_words:
                            migrated_languages['en'] = {
                                f"en:{lemma}": card for lemma, card in en_words.items()
                            }
                        if de_words:
                            migrated_languages['de'] = {
                                f"de:{lemma}": card for lemma, card in de_words.items()
                            }
                        cache['languages'] = migrated_languages
                        cache['version'] = 2
                    total = sum(len(words) for words in cache['languages'].values())
                    if verbose:
                        details = ', '.join(
                            f"{lang.upper()}: {len(words)}" for lang, words in cache['languages'].items()
                        ) or "leer"
                        print(f"  📦 Cache loaded: {total} words ({details})")
                else:
                    if verbose:
                        print("  ⚠️  Invalid cache format, starting fresh")
        
        except Exception as e:
            if verbose:
                print(f"  ⚠️  Cache load error: {e}, starting fresh")
    else:
        if verbose:
            print(f"  📦 No cache file found, starting fresh")
    
    return cache


def save_translated_cache(cache: Dict, cache_file: str, verbose: bool = False):
    """
    Save translation cache to JSON file
    
    Args:
        cache: Cache dictionary
        cache_file: Path to cache JSON file
        verbose: Enable verbose output
    """
    try:
        # Create directory if needed
        cache_path = Path(cache_file)
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Save with pretty formatting
        with open(cache_file, 'w', encoding='utf-8') as f:
            json.dump(cache, f, indent=2, ensure_ascii=False)
        
        language_counts = {lang: len(entries) for lang, entries in cache.get('languages', {}).items()}
        total = sum(language_counts.values())

        if verbose:
            details = ', '.join(f"{lang.upper()}: {count}" for lang, count in language_counts.items()) or "leer"
            print(f"  💾 Cache saved: {total} words ({details})")
    
    except Exception as e:
        if verbose:
            print(f"  ❌ Cache save error: {e}")


def _language_bucket(cache: Dict, language: str) -> Dict:
    languages = cache.setdefault('languages', {})
    return languages.setdefault(language, {})


def add_to_cache(cards: list, words: list, language: str, cache: Dict,
                 native_language: str, verbose: bool = False):
    """
    Add translated vocabulary cards to cache
    Matches each card with the corresponding word from the batch
    Checks for duplicates based on Lemma (case-insensitive)
    
    SCHEMA COMPATIBILITY:
    - NEW schema (from Gemini): Lemma, Word, Translation, Definition, Usage, Book, Notes
    - Fallback to OLD schema: Original_word, EN_lemma/DE_lemma, DE_gloss, Context_HTML
    
    IMPORTANT: Word IDs are generated from Lemma
    This ensures "Pity" and "pity" get the same ID "en:pity"
    
    Args:
        cards: List of card dictionaries from Gemini
        words: List of word dictionaries from batch (for metadata)
        language: 'en' or 'de'
        cache: Cache dictionary (modified in-place)
        verbose: Enable verbose output
    """
    from .normalization import normalize_de_gloss

    language = language.lower()
    native_language = native_language.lower()
    lemma_key = build_field_key(language, 'lemma')
    gloss_key = build_field_key(native_language, 'gloss')
    bucket = _language_bucket(cache, language)
    
    # Create mapping: normalized word -> word dict (for metadata)
    # Support both 'Word' (new) and 'word' (old batch format)
    word_to_metadata = {}
    for word in words:
        normalized = word.get('word', '').lower().strip()
        word_to_metadata[normalized] = word
    
    # Create Lemma index for duplicate detection
    existing_lemmas = {}
    for word_id, card in bucket.items():
        lemma = card.get(lemma_key, '').lower().strip()
        if lemma:
            existing_lemmas[lemma] = word_id
    
    # Match each card with the corresponding word
    matched_count = 0
    unmatched_cards = []
    skipped_duplicates = 0
    
    for card in cards:
        # Get word from card
        original_word = card.get('Original_word', '').lower().strip()
        
        if not original_word:
            unmatched_cards.append("(card without Original_word)")
            continue
        
        # Get Lemma from card based on language
        lemma = card.get(lemma_key, '').lower().strip()
        
        if not lemma:
            unmatched_cards.append(f"{original_word} (no lemma)")
            continue
        
        # Check for duplicate based on Lemma
        if lemma in existing_lemmas:
            # Duplicate found - skip
            skipped_duplicates += 1
            if verbose:
                print(f"    ⚠️  Duplicate skipped: '{lemma}' (already exists as {existing_lemmas[lemma]})")
            continue
        
        # Normalize German translation (only for EN words)
        if native_language == 'de' and gloss_key in card:
            card[gloss_key] = normalize_de_gloss(card[gloss_key])
        
        # Get word dict for metadata (Book from batch has priority)
        word_dict = word_to_metadata.get(original_word)
        
        if word_dict and word_dict.get('book') and word_dict['book'] != 'Unknown':
            # Book already normalized in process_language_batch
            if 'Book' not in card or card['Book'] == 'Unknown':
                card['Book'] = word_dict.get('book', 'Unknown')
        
        # Ensure Book field exists
        if 'Book' not in card:
            card['Book'] = 'Unknown'
        
        # Generate Word-ID from Lemma
        word_id = f"{language}:{lemma}"

        # No duplicate - add
        bucket[word_id] = card
        existing_lemmas[lemma] = word_id
        matched_count += 1
    
    if verbose:
        print(f"\n   ✓ {matched_count} cards successfully matched")
        if skipped_duplicates > 0:
            print(f"   ⚠️  {skipped_duplicates} duplicates skipped (already in cache)")
        if unmatched_cards:
            print(f"   ⚠️  {len(unmatched_cards)} cards without match: {', '.join(unmatched_cards)}")


def is_word_translated(cache: Dict, lemma: str, language: str) -> bool:
    """
    Check if word is already in cache (by lemma)
    
    Args:
        cache: Cache dictionary
        lemma: Word lemma (lowercase)
        language: 'en' or 'de'
        
    Returns:
        True if word exists in cache
    """
    languages = cache.get('languages', {})
    bucket = languages.get(language.lower(), {})
    lemma_lower = lemma.lower().strip()
    word_id_new = f"{language.lower()}:{lemma_lower}"

    if word_id_new in bucket:
        return True

    lemma_key = build_field_key(language, 'lemma')
    for card in bucket.values():
        cached_lemma = card.get(lemma_key, '').lower().strip()
        if cached_lemma == lemma_lower:
            return True
    
    return False


def get_from_cache(cache: Dict, lemma: str, language: str) -> Optional[Dict]:
    """
    Retrieve card from cache
    
    Args:
        cache: Cache dictionary
        lemma: Word lemma (lowercase)
        language: 'en' or 'de'
        
    Returns:
        Card dictionary or None if not found
    """
    bucket = cache.get('languages', {}).get(language.lower(), {})
    word_id = f"{language.lower()}:{lemma.lower()}"
    return bucket.get(word_id)


def remove_from_cache(cache: Dict, lemma: str, language: str) -> bool:
    """
    Remove word from cache
    
    Args:
        cache: Cache dictionary (modified in-place)
        lemma: Word lemma (lowercase)
        language: 'en' or 'de'
        
    Returns:
        True if word was found and removed
    """
    bucket = cache.get('languages', {}).get(language.lower(), {})
    word_id = f"{language.lower()}:{lemma.lower()}"
    if word_id in bucket:
        del bucket[word_id]
        return True
    
    return False


def merge_caches(cache1: Dict, cache2: Dict) -> Dict:
    """
    Merge two caches (cache2 overwrites cache1 on conflicts)
    
    Args:
        cache1: First cache dictionary
        cache2: Second cache dictionary (has priority)
        
    Returns:
        Merged cache dictionary
    """
    merged = {
        'version': 2,
        'languages': {}
    }

    for cache in (cache1, cache2):
        for lang, words in cache.get('languages', {}).items():
            bucket = merged['languages'].setdefault(lang, {})
            bucket.update(words)

    return merged


def get_cache_stats(cache: Dict) -> Dict:
    """
    Get cache statistics
    
    Args:
        cache: Cache dictionary
        
    Returns:
        Statistics dictionary
    """
    languages = cache.get('languages', {})
    stats = {lang: len(entries) for lang, entries in languages.items()}
    stats['total'] = sum(stats.values())
    return stats
