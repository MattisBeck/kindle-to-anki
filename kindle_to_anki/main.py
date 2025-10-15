"""
Main entry point for Kindle to Anki converter
Orchestrates the entire ETL pipeline: Database → Gemini → TSV → APKG
"""

import time
from pathlib import Path
from typing import List, Dict

# Import all modules
from .config import CONFIG, SPACY_MODELS
from .database import connect_to_db, get_vocabulary_data, separate_by_language
from .normalization import lemmatize_word, normalize_book_title, load_book_titles_from_cache
from .gemini_api import setup_gemini_api, process_batch_with_gemini
from .cache import (load_translated_cache, save_translated_cache, add_to_cache, 
                    is_word_translated, get_cache_stats)
from .export import create_all_tsv_files, export_to_apkg, remove_duplicates, filter_valid_cards
from .utils import log_error, print_stats, count_api_calls, save_progress, load_progress

# spaCy models - will be loaded on first use
nlp_en = None
nlp_de = None
spacy_loaded = False


def load_spacy_models(verbose: bool = False):
    """Load spaCy models on demand"""
    global nlp_en, nlp_de, spacy_loaded
    
    if spacy_loaded:
        return
    
    try:
        import spacy
        
        for lang, model_name in SPACY_MODELS.items():
            try:
                if lang == 'en':
                    if verbose:
                        print(f"  📚 Loading spaCy model: {model_name}")
                    nlp_en = spacy.load(model_name)
                elif lang == 'de':
                    if verbose:
                        print(f"  📚 Loading spaCy model: {model_name}")
                    nlp_de = spacy.load(model_name)
            except OSError:
                if verbose:
                    print(f"  ⚠️  spaCy model '{model_name}' not found!")
                    print(f"     Install with: python -m spacy download {model_name}")
        
        spacy_loaded = True
    
    except ImportError:
        if verbose:
            print("  ⚠️  spaCy not installed! Lemmatization will use Gemini fallback.")
            print("     Install with: pip install spacy")
        spacy_loaded = True


def process_language_batch(words: List[Dict], language: str, genai, cache: Dict, 
                           verbose: bool = False) -> List[Dict]:
    """
    Process a batch of words for a specific language
    
    Args:
        words: List of word dictionaries from database
        language: 'en' or 'de'
        genai: Gemini API instance
        cache: Translation cache
        verbose: Enable verbose output
        
    Returns:
        List of processed cards
    """
    if not words:
        return []
    
    # Lemmatize words and prepare batch
    nlp = nlp_en if language == 'en' else nlp_de
    
    words_batch = []
    for word_data in words:
        word = word_data['word']
        lemma = lemmatize_word(word, language, nlp_en, nlp_de)
        
        # Normalize book title
        book_title = normalize_book_title(
            word_data.get('book', 'Unknown'),
            author_from_db=word_data.get('authors'),
            genai_instance=genai,
            verbose=verbose
        )
        
        words_batch.append({
            'word': word,
            'lemma': lemma,
            'usage': word_data.get('usage', ''),
            'book': book_title
        })
    
    # Split into batches for API
    batch_size = CONFIG.get('BATCH_SIZE', 20)
    batches = [words_batch[i:i + batch_size] for i in range(0, len(words_batch), batch_size)]
    
    all_cards = []
    quota_exceeded = False
    
    lang_flag = "🇬🇧" if language == 'en' else "🇩🇪"
    lang_name = "English" if language == 'en' else "German"
    
    for i, batch in enumerate(batches, 1):
        if quota_exceeded:
            if verbose:
                print(f"  ⏸️  Batch {i}/{len(batches)} skipped (quota limit)")
            continue
        
        if verbose:
            print(f"  {lang_flag} Batch {i}/{len(batches)} ({len(batch)} words)...", end=" ")
        
        # Process with Gemini
        cards = process_batch_with_gemini(batch, language, genai, verbose=verbose, batch_num=i)
        
        if cards:
            all_cards.extend(cards)
            
            # Add to cache (with duplicate detection and book normalization)
            add_to_cache(cards, batch, language, cache, verbose=verbose)
            
            # Save cache after each batch
            save_translated_cache(cache, CONFIG['TRANSLATED_CACHE'], verbose=False)
            
            if verbose:
                print(f"✅ {len(cards)} cards")
        else:
            # Check if quota was exceeded
            if verbose:
                print("❌ Failed")
            
        # Delay between batches
        if i < len(batches) and not quota_exceeded:
            delay = CONFIG.get('DELAY_BETWEEN_BATCHES', 4.5)
            time.sleep(delay)
    
    return all_cards


def main():
    """
    Main entry point for Kindle to Anki converter
    """
    start_time = time.time()
    
    verbose = CONFIG.get('VERBOSE', False)
    
    print("=" * 70)
    print("Kindle to Anki Converter v2.0")
    print("=" * 70)
    print()
    
    # 1. Configuration overview
    if verbose:
        print("📋 Configuration:")
        print(f"  - Database:      {CONFIG['VOCAB_DB_PATH']}")
        print(f"  - TSV output:    {CONFIG['TSV_OUTPUT_DIR']}")
        print(f"  - APKG output:   {CONFIG['APKG_OUTPUT_DIR']}")
        print(f"  - Batch size:    {CONFIG['BATCH_SIZE']}")
        print(f"  - Batch delay:   {CONFIG['DELAY_BETWEEN_BATCHES']}s")
        print(f"  - Max retries:   {CONFIG['MAX_RETRIES']}")
        print(f"  - API key set:   {'✅' if CONFIG['GEMINI_API_KEY'] else '❌'}")
        print(f"  - Skip cached:   {'✅' if CONFIG['SKIP_TRANSLATED'] else '❌'}")
        print(f"  - Create APKG:   {'✅' if CONFIG['CREATE_APKG'] else '❌'}")
        print()
    
    # 2. Load vocabulary from database
    print("📚 Loading vocabulary from database...")
    try:
        conn = connect_to_db(CONFIG['VOCAB_DB_PATH'])
        vocab_data = get_vocabulary_data(conn)
        en_words, de_words = separate_by_language(vocab_data)
        conn.close()
        
        print(f"  - Total: {len(vocab_data)} words")
        print(f"  - English: {len(en_words)} words")
        print(f"  - German: {len(de_words)} words")
        print()
    
    except Exception as e:
        print(f"❌ Database error: {e}")
        log_error(f"Database error: {e}", CONFIG['ERROR_LOG'], verbose)
        return
    
    # 2.5 Load spaCy models (only if needed)
    if en_words or de_words:
        if verbose:
            print("📚 Loading NLP models...")
        load_spacy_models(verbose)
        if verbose:
            print()
    
    # 3. Load translation cache
    print("📦 Loading cache...")
    cache = load_translated_cache(CONFIG['TRANSLATED_CACHE'], verbose=verbose)
    
    # Load book titles into RAM for consistent formatting
    load_book_titles_from_cache(cache, verbose=verbose)
    
    # Load progress (optional resume support)
    progress = load_progress(CONFIG.get('PROGRESS_FILE', 'anki_cards/progress.json'), verbose=False)
    
    # Filter already translated words (with lemmatization!)
    if CONFIG.get('SKIP_TRANSLATED'):
        en_original = len(en_words)
        de_original = len(de_words)
        
        # Lemmatize words BEFORE checking cache (critical!)
        for w in en_words:
            w['lemma'] = lemmatize_word(w['word'], 'en', nlp_en, nlp_de)
        for w in de_words:
            w['lemma'] = lemmatize_word(w['word'], 'de', nlp_en, nlp_de)
        
        # Filter by lemma (not by original word!)
        en_words = [w for w in en_words if not is_word_translated(cache, w['lemma'], 'en')]
        de_words = [w for w in de_words if not is_word_translated(cache, w['lemma'], 'de')]
        
        en_skipped = en_original - len(en_words)
        de_skipped = de_original - len(de_words)
        
        if verbose:
            print(f"  - Skipped {en_skipped} cached English words")
            print(f"  - Skipped {de_skipped} cached German words")
        
        print(f"  - New English words: {len(en_words)}")
        print(f"  - New German words: {len(de_words)}")
        print()
    
    # 4. Initialize Gemini API (or skip for DRY_RUN)
    if CONFIG.get('DRY_RUN'):
        genai = None
        print("⚠️  DRY RUN mode - no API calls")
        print("   Skipping Gemini processing...")
        print()
        en_cards_new = []
        de_cards_new = []
    else:
        print("🤖 Initializing Gemini API...")
        genai = setup_gemini_api(CONFIG['GEMINI_API_KEY'], verbose=verbose)
        
        if not genai:
            print("❌ Failed to initialize Gemini API")
            return
        
        print()
        
        # 5. Process English words
        en_cards_new = []
        if CONFIG.get('CREATE_EN_DE_CARDS') and en_words:
            print(f"🇬🇧 Processing {len(en_words)} English words...")
            en_cards_new = process_language_batch(en_words, 'en', genai, cache, verbose=verbose)
            print()
        
        # 6. Process German words
        de_cards_new = []
        if CONFIG.get('CREATE_DE_DE_CARDS') and de_words:
            print(f"🇩🇪 Processing {len(de_words)} German words...")
            de_cards_new = process_language_batch(de_words, 'de', genai, cache, verbose=verbose)
            print()
    
    # 7. Combine new cards with cached cards
    all_en_cards = list(cache.get('en_words', {}).values())
    all_de_cards = list(cache.get('de_words', {}).values())
    
    # 8. Remove duplicates and validate
    all_en_cards = remove_duplicates(all_en_cards, language='en')
    all_de_cards = remove_duplicates(all_de_cards, language='de')
    
    all_en_cards = filter_valid_cards(all_en_cards, 'en_de', verbose=verbose)
    all_de_cards = filter_valid_cards(all_de_cards, 'de_de', verbose=verbose)
    
    # 9. Create TSV files
    print("📝 Creating TSV files...")
    create_all_tsv_files(all_en_cards, all_de_cards, verbose=verbose)
    print()
    
    # 10. Create APKG packages (optional)
    if CONFIG.get('CREATE_APKG'):
        print("📦 Creating APKG packages...")
        try:
            export_to_apkg(
                CONFIG['TSV_OUTPUT_DIR'],
                CONFIG['APKG_OUTPUT_DIR'],
                verbose=verbose
            )
            print()
        except Exception as e:
            print(f"⚠️  APKG export failed: {e}")
            print("   TSV files are available for manual import")
            print()
    
    # 11. Print final statistics
    processing_time = time.time() - start_time
    cache_stats = get_cache_stats(cache)
    
    print_stats(all_en_cards, all_de_cards, cache_stats, processing_time, verbose=True)
    
    print("📁 Output:")
    if CONFIG.get('CREATE_APKG'):
        print(f"   APKG files: {Path(CONFIG['APKG_OUTPUT_DIR']).absolute()}")
    print(f"   TSV files:  {Path(CONFIG['TSV_OUTPUT_DIR']).absolute()}")
    print()
    
    print("💡 Tip: On next run, cached words are automatically skipped!")
    print("   Only new vocabulary will be processed.")
    print()


if __name__ == "__main__":
    main()
