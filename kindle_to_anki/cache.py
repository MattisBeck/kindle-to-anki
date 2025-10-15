"""
Cache management for translations and book metadata
"""

import json
import os
from pathlib import Path
from typing import Dict, Optional


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
    cache = {
        'en_words': {},
        'de_words': {}
    }
    
    if os.path.exists(cache_file):
        try:
            with open(cache_file, 'r', encoding='utf-8') as f:
                loaded_cache = json.load(f)
                
                # Validate structure
                if isinstance(loaded_cache, dict):
                    cache['en_words'] = loaded_cache.get('en_words', {})
                    cache['de_words'] = loaded_cache.get('de_words', {})
                    
                    en_count = len(cache['en_words'])
                    de_count = len(cache['de_words'])
                    total = en_count + de_count
                    
                    if verbose:
                        print(f"  📦 Cache loaded: {total} words (EN: {en_count}, DE: {de_count})")
                else:
                    if verbose:
                        print(f"  ⚠️  Invalid cache format, starting fresh")
        
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
        
        en_count = len(cache.get('en_words', {}))
        de_count = len(cache.get('de_words', {}))
        total = en_count + de_count
        
        if verbose:
            print(f"  💾 Cache saved: {total} words (EN: {en_count}, DE: {de_count})")
    
    except Exception as e:
        if verbose:
            print(f"  ❌ Cache save error: {e}")


def add_to_cache(cards: list, words: list, language: str, cache: Dict, 
                 verbose: bool = False):
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
    
    cache_key = 'en_words' if language == 'en' else 'de_words'
    
    # Create mapping: normalized word -> word dict (for metadata)
    # Support both 'Word' (new) and 'word' (old batch format)
    word_to_metadata = {}
    for word in words:
        normalized = word.get('word', '').lower().strip()
        word_to_metadata[normalized] = word
    
    # Create Lemma index for duplicate detection
    existing_lemmas = {}
    for word_id, card in cache.get(cache_key, {}).items():
        # Get lemma based on language
        lemma_key = 'EN_lemma' if language == 'en' else 'DE_lemma'
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
        lemma_key = 'EN_lemma' if language == 'en' else 'DE_lemma'
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
        if language == 'en' and 'DE_gloss' in card:
            card['DE_gloss'] = normalize_de_gloss(card['DE_gloss'])
        
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
        prefix = 'en' if language == 'en' else 'de'
        word_id = f"{prefix}:{lemma}"
        
        # No duplicate - add
        cache[cache_key][word_id] = card
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
    key = 'en_words' if language == 'en' else 'de_words'
    lemma_lower = lemma.lower().strip()
    
    # Check both new format (key = "en:lemma") and old format
    word_id_new = f"{'en' if language == 'en' else 'de'}:{lemma_lower}"
    
    if word_id_new in cache.get(key, {}):
        return True
    
    # Fallback: check if any cached card has this lemma
    for card in cache.get(key, {}).values():
        lemma_key = 'EN_lemma' if language == 'en' else 'DE_lemma'
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
    key = 'en_words' if language == 'en' else 'de_words'
    return cache.get(key, {}).get(lemma.lower())


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
    key = 'en_words' if language == 'en' else 'de_words'
    lemma_lower = lemma.lower()
    
    if lemma_lower in cache.get(key, {}):
        del cache[key][lemma_lower]
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
        'en_words': {},
        'de_words': {}
    }
    
    # Merge EN words
    merged['en_words'].update(cache1.get('en_words', {}))
    merged['en_words'].update(cache2.get('en_words', {}))
    
    # Merge DE words
    merged['de_words'].update(cache1.get('de_words', {}))
    merged['de_words'].update(cache2.get('de_words', {}))
    
    return merged


def get_cache_stats(cache: Dict) -> Dict:
    """
    Get cache statistics
    
    Args:
        cache: Cache dictionary
        
    Returns:
        Statistics dictionary
    """
    en_count = len(cache.get('en_words', {}))
    de_count = len(cache.get('de_words', {}))
    
    return {
        'total': en_count + de_count,
        'en': en_count,
        'de': de_count
    }
