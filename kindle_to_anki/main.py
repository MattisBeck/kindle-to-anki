"""
Main entry point for Kindle to Anki converter
Orchestrates the entire ETL pipeline: Database → Gemini → TSV → APKG
"""

import time
from pathlib import Path
from typing import Dict, List, Sequence

# Import all modules
from .config import CONFIG, SPACY_MODELS
from .helpers import (
    get_language_meta,
    validate_language_configuration,
    validate_api_key,
)
from .database import connect_to_db, get_vocabulary_data, filter_vocabulary_by_language
from .normalization import lemmatize_word, normalize_book_title, load_book_titles_from_cache
from .gemini_api import setup_gemini_api, process_batch_with_gemini
from .cache import (
    add_to_cache,
    get_cache_stats,
    is_word_translated,
    load_translated_cache,
    save_translated_cache,
)
from .export import create_all_tsv_files, export_to_apkg, filter_valid_cards, remove_duplicates
from .utils import log_error, load_progress, print_stats

# spaCy models - lazily loaded per language
NLP_MODELS: Dict[str, object] = {}
SPACY_IMPORT_FAILED = False


def load_spacy_models(languages: Sequence[str], verbose: bool = False):
    """Ensure spaCy models for the requested languages are loaded."""

    global SPACY_IMPORT_FAILED

    normalized_languages = [lang.lower() for lang in languages if lang]
    if not normalized_languages or SPACY_IMPORT_FAILED:
        return

    try:
        import spacy  # type: ignore
    except ImportError:
        SPACY_IMPORT_FAILED = True
        print("  ⚠️  spaCy not installed! Lemmatization will fall back to lowercase only.")
        print("     Install with: pip install spacy")
        return

    for lang in normalized_languages:
        if lang in NLP_MODELS:
            continue

        model_name = SPACY_MODELS.get(lang)
        if not model_name:
            print(f"  ⚠️  No spaCy model configured for '{lang}'.")
            NLP_MODELS[lang] = None
            continue

        try:
            if verbose:
                print(f"  📚 Loading spaCy model: {model_name}")
            NLP_MODELS[lang] = spacy.load(model_name)
        except OSError:
            NLP_MODELS[lang] = None
            # Always show error messages for missing models (critical info!)
            print(f"  ⚠️  spaCy model '{model_name}' not found!")
            print(f"     Install with: python -m spacy download {model_name}")


def process_language_batch(words: List[Dict], language: str,
                           native_language: str, target_language: str,
                           genai, cache: Dict, verbose: bool = False) -> List[Dict]:
    """Process a batch of vocabulary entries for a specific language."""

    if not words:
        return []

    language = language.lower()
    native_language = native_language.lower()
    target_language = target_language.lower()

    words_batch: List[Dict] = []
    for word_data in words:
        word = word_data['word']
        lemma = word_data.get('lemma') or lemmatize_word(
            word,
            language,
            nlp_models=NLP_MODELS,
        )

        book_title = normalize_book_title(
            word_data.get('book', 'Unknown'),
            author_from_db=word_data.get('authors'),
            genai_instance=genai,
            verbose=verbose,
        )

        words_batch.append({
            'word': word,
            'lemma': lemma,
            'usage': word_data.get('usage', ''),
            'book': book_title,
        })

    batch_size = CONFIG.get('BATCH_SIZE', 20)
    batches = [words_batch[i:i + batch_size] for i in range(0, len(words_batch), batch_size)]

    all_cards: List[Dict] = []
    lang_flag = f"[{language.upper()}]"

    for i, batch in enumerate(batches, 1):
        if verbose:
            print(f"  {lang_flag} Batch {i}/{len(batches)} ({len(batch)} words)...", end=" ")

        # Measure API response time for smart delay calculation
        batch_start = time.time()
        cards = process_batch_with_gemini(
            batch,
            language,
            native_language,
            target_language,
            genai,
            verbose=verbose,
            batch_num=i,
        )
        batch_duration = time.time() - batch_start

        if cards:
            all_cards.extend(cards)
            add_to_cache(cards, batch, language, cache, native_language, verbose=verbose)
            save_translated_cache(cache, CONFIG['TRANSLATED_CACHE'], verbose=False)

            if verbose:
                print(f"✅ {len(cards)} cards")
        else:
            if verbose:
                print("❌ Failed")

        # Smart delay: only wait the remaining time to reach DELAY_BETWEEN_BATCHES
        if i < len(batches):
            delay_target = CONFIG.get('DELAY_BETWEEN_BATCHES', 4.5)
            remaining_delay = max(0, delay_target - batch_duration)
            if remaining_delay > 0:
                if verbose:
                    print(f"  ⏱️  API took {batch_duration:.2f}s, waiting {remaining_delay:.2f}s (target: {delay_target}s)")
                time.sleep(remaining_delay)
            else:
                if verbose:
                    print(f"  ⏱️  API took {batch_duration:.2f}s, no additional delay needed (target: {delay_target}s)")

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
    
    # Validate API key before any processing
    validate_api_key()
    
    native_language, target_language = validate_language_configuration()
    native_meta = get_language_meta(native_language)
    target_meta = get_language_meta(target_language)

    if verbose:
        print("📋 Configuration:")
        print(f"  - Database:            {CONFIG['VOCAB_DB_PATH']}")
        print(f"  - TSV output:          {CONFIG['TSV_OUTPUT_DIR']}")
        print(f"  - APKG output:         {CONFIG['APKG_OUTPUT_DIR']}")
        print(f"  - Native language:     {native_meta['english_name']} ({native_language.upper()})")
        print(f"  - Target language:     {target_meta['english_name']} ({target_language.upper()})")
        print(f"  - Batch size:          {CONFIG['BATCH_SIZE']}")
        print(f"  - Batch delay:         {CONFIG['DELAY_BETWEEN_BATCHES']}s")
        print(f"  - Skip translated:     {'✅' if CONFIG.get('SKIP_TRANSLATED') else '❌'}")
        print(f"  - Create APKG:         {'✅' if CONFIG.get('CREATE_APKG') else '❌'}")
        print(f"  - Decks (foreign→native / native→foreign / native→native): "
              f"{CONFIG.get('CREATE_FOREIGN_TO_NATIVE', True)} / "
              f"{CONFIG.get('CREATE_NATIVE_TO_FOREIGN', True)} / "
              f"{CONFIG.get('CREATE_NATIVE_TO_NATIVE', True)}")
        print()

    print("📚 Loading vocabulary from database...")
    try:
        conn = connect_to_db(CONFIG['VOCAB_DB_PATH'])
        vocab_data = get_vocabulary_data(conn)
        conn.close()

        target_words = filter_vocabulary_by_language(vocab_data, target_language)
        native_words = filter_vocabulary_by_language(vocab_data, native_language)

        print(f"  - Total entries: {len(vocab_data)}")
        print(f"  - {target_meta['english_name']} ({target_language.upper()}): {len(target_words)} words")
        if native_language != target_language:
            print(f"  - {native_meta['english_name']} ({native_language.upper()}): {len(native_words)} words")
        
        # Check for unexpected languages
        configured_languages = {native_language, target_language}
        found_languages = set()
        for entry in vocab_data:
            lang = entry.get('lang_normalized', '').lower()
            if lang and lang not in configured_languages:
                found_languages.add(lang)
        
        if found_languages:
            print()
            print("  ⚠️  Warning: Found vocabulary in unsupported languages:")
            for lang in sorted(found_languages):
                lang_count = sum(1 for e in vocab_data if e.get('lang_normalized', '').lower() == lang)
                try:
                    lang_meta = get_language_meta(lang)
                    lang_name = lang_meta['english_name']
                except ValueError:
                    lang_name = lang.upper()
                print(f"      - {lang_name} ({lang.upper()}): {lang_count} words")
            print(f"      These words will be IGNORED (not SOURCE or TARGET language).")
        
        print()

    except Exception as exc:
        print(f"❌ Database error: {exc}")
        log_error(f"Database error: {exc}", CONFIG['ERROR_LOG'], verbose)
        return

    process_foreign_decks = CONFIG.get('CREATE_FOREIGN_TO_NATIVE', True) or CONFIG.get('CREATE_NATIVE_TO_FOREIGN', True)
    process_native_deck = CONFIG.get('CREATE_NATIVE_TO_NATIVE', True)

    languages_to_load: List[str] = []
    if process_foreign_decks and target_words:
        languages_to_load.append(target_language)
    if process_native_deck and native_words:
        languages_to_load.append(native_language)

    if languages_to_load:
        if verbose:
            print("📚 Loading NLP models...")
        load_spacy_models(languages_to_load, verbose=verbose)
        if verbose:
            print()

    print("📦 Loading cache...")
    cache = load_translated_cache(CONFIG['TRANSLATED_CACHE'], verbose=verbose)
    load_book_titles_from_cache(cache, verbose=verbose)

    load_progress(CONFIG.get('PROGRESS_FILE', 'anki_cards/progress.json'), verbose=False)

    if CONFIG.get('SKIP_TRANSLATED'):
        if process_foreign_decks and target_words:
            original = len(target_words)
            for word in target_words:
                word['lemma'] = lemmatize_word(word['word'], target_language, nlp_models=NLP_MODELS)
            target_words = [w for w in target_words if not is_word_translated(cache, w['lemma'], target_language)]
            skipped = original - len(target_words)
            print(f"  - Skipped {skipped} cached {target_meta['english_name']} words")
            print(f"  - New {target_meta['english_name']} words: {len(target_words)}")

        if process_native_deck and native_words:
            original_native = len(native_words)
            for word in native_words:
                word['lemma'] = lemmatize_word(word['word'], native_language, nlp_models=NLP_MODELS)
            native_words = [w for w in native_words if not is_word_translated(cache, w['lemma'], native_language)]
            skipped_native = original_native - len(native_words)
            print(f"  - Skipped {skipped_native} cached {native_meta['english_name']} words")
            print(f"  - New {native_meta['english_name']} words: {len(native_words)}")

        print()

    if CONFIG.get('DRY_RUN'):
        genai = None
        print("⚠️  DRY RUN mode - no API calls")
        print("   Skipping Gemini processing...")
        print()
    else:
        print("🤖 Initializing Gemini API...")
        genai = setup_gemini_api(CONFIG['GEMINI_API_KEY'], verbose=verbose)
        if not genai:
            print("❌ Failed to initialize Gemini API")
            return
        print()

        if process_foreign_decks and target_words:
            print(f"� Processing {len(target_words)} {target_meta['english_name']} words...")
            process_language_batch(
                target_words,
                target_language,
                native_language,
                target_language,
                genai,
                cache,
                verbose=verbose,
            )
            print()

        if process_native_deck and native_words:
            print(f"� Processing {len(native_words)} {native_meta['english_name']} words...")
            process_language_batch(
                native_words,
                native_language,
                native_language,
                target_language,
                genai,
                cache,
                verbose=verbose,
            )
            print()

    language_buckets = cache.get('languages', {})
    foreign_cards_all = list(language_buckets.get(target_language, {}).values()) if process_foreign_decks else []
    native_cards_all = list(language_buckets.get(native_language, {}).values()) if process_native_deck else []

    foreign_cards = remove_duplicates(foreign_cards_all, target_language) if foreign_cards_all else []
    native_cards = remove_duplicates(native_cards_all, native_language) if native_cards_all else []

    if foreign_cards:
        foreign_cards = filter_valid_cards(foreign_cards, 'foreign_native', native_language, target_language, verbose=verbose)
    if native_cards:
        native_cards = filter_valid_cards(native_cards, 'native_native', native_language, target_language, verbose=verbose)

    print("📝 Creating TSV files...")
    create_all_tsv_files(foreign_cards, native_cards, native_language, target_language, verbose=verbose)
    print()

    if CONFIG.get('CREATE_APKG'):
        print("📦 Creating APKG packages...")
        try:
            export_to_apkg(CONFIG['TSV_OUTPUT_DIR'], CONFIG['APKG_OUTPUT_DIR'], verbose=verbose)
            print()
        except Exception as exc:
            print(f"⚠️  APKG export failed: {exc}")
            print("   TSV files are available for manual import")
            print()

    processing_time = time.time() - start_time
    cache_stats = get_cache_stats(cache)

    deck_counts: Dict[str, int] = {}
    if foreign_cards:
        if CONFIG.get('CREATE_FOREIGN_TO_NATIVE', True):
            deck_counts[f"{target_language.upper()}→{native_language.upper()}"] = len(foreign_cards)
        if CONFIG.get('CREATE_NATIVE_TO_FOREIGN', True):
            deck_counts[f"{native_language.upper()}→{target_language.upper()}"] = len(foreign_cards)
    if native_cards and CONFIG.get('CREATE_NATIVE_TO_NATIVE', True):
        deck_counts[f"{native_language.upper()}→{native_language.upper()}"] = len(native_cards)

    print_stats(deck_counts, cache_stats, processing_time, verbose=True)

    print("📁 Output:")
    if CONFIG.get('CREATE_APKG'):
        print(f"   APKG files: {Path(CONFIG['APKG_OUTPUT_DIR']).absolute()}")
    print(f"   TSV files:  {Path(CONFIG['TSV_OUTPUT_DIR']).absolute()}")
    print()

    if deck_counts:
        print("🔁 Re-importing updates existing cards thanks to stable GUIDs.")
    print("💡 Tip: On next run, cached words are automatically skipped!")
    print("   Only new vocabulary will be processed.")
    print()


if __name__ == "__main__":
    main()
