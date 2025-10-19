"""
Configuration settings for Kindle to Anki converter
"""
CONFIG = {
    # Gemini API Key (required)
    'GEMINI_API_KEY': "", 
    
    # Language configuration
    # SOURCE_LANGUAGE = Native language (cards & prompts default to this language)
    # TARGET_LANGUAGE = Language you are learning / Kindle book language
    'SOURCE_LANGUAGE': 'de',
    'TARGET_LANGUAGE': 'es',

    # Paths
    'VOCAB_DB_PATH': 'put_vocab_db_here/vocab.db',  # Path to Kindle vocabulary database
    'TSV_OUTPUT_DIR': 'anki_cards/tsv_files',  # TSV files for Anki
    'APKG_OUTPUT_DIR': 'anki_cards/apkg_files',  # APKG packages for direct import
    'PROGRESS_FILE': 'anki_cards/progress.json',  # Progress tracking
    'ERROR_LOG': 'anki_cards/errors.log',  # Error log
    'TRANSLATED_CACHE': 'anki_cards/translated_cache.json',  # Cache for translated vocabulary
    
    # Batch settings (to comply with current API limits: RPM 15, TPM 1,000,000, RPD 200; those may change)
    'BATCH_SIZE': 20,  # Words per batch
    'DELAY_BETWEEN_BATCHES': 4.5,  # Seconds delay between batches (for RPM 15 = ~4-5 sec)
    'MAX_RETRIES': 3,  # Number of retry attempts on API errors
    'RETRY_DELAY': 10,  # Seconds to wait before retry
    
    # Output options
    'CREATE_NATIVE_TO_FOREIGN': True,  # Native → Foreign deck (e.g. DE → EN)
    'CREATE_FOREIGN_TO_NATIVE': True,  # Foreign → Native deck (e.g. EN → DE)
    'CREATE_NATIVE_TO_NATIVE': True,  # Native → Native deck (monolingual)
    'SKIP_DUPLICATES': True,  # Skip duplicate vocabulary
    'SKIP_TRANSLATED': True,  # Skip already translated vocabulary
    'CREATE_APKG': True,  # Automatically create APKG packages (requires genanki)
    
    # Debugging
    'VERBOSE': True,  # Detailed output
    'DRY_RUN': False,  # If True, no API calls are made (for testing)
    'SAVE_RAW_RESPONSES': False,  # Save API responses (for debugging)
    'SAVE_RAW_INPUTS': False,  # Save API prompts (for debugging)
}

# Supported languages
SUPPORTED_LANGUAGES = {
    'de': {
        'autonym': 'Deutsch',
        'english_name': 'German',
        'german_name': 'Deutsch',
        'gemini_label': 'Deutsch',
        'spacy_model': 'de_core_news_sm',
        'spacy_download': 'python -m spacy download de_core_news_sm',
    },
    'en': {
        'autonym': 'English',
        'english_name': 'English',
        'german_name': 'Englisch',
        'gemini_label': 'Englisch',
        'spacy_model': 'en_core_web_sm',
        'spacy_download': 'python -m spacy download en_core_web_sm',
    },
    'fr': {
        'autonym': 'Français',
        'english_name': 'French',
        'german_name': 'Französisch',
        'gemini_label': 'Französisch',
        'spacy_model': 'fr_core_news_sm',
        'spacy_download': 'python -m spacy download fr_core_news_sm',
    },
    'es': {
        'autonym': 'Español',
        'english_name': 'Spanish',
        'german_name': 'Spanisch',
        'gemini_label': 'Spanisch',
        'spacy_model': 'es_core_news_sm',
        'spacy_download': 'python -m spacy download es_core_news_sm',
    },
    'pl': {
        'autonym': 'Polski',
        'english_name': 'Polish',
        'german_name': 'Polnisch',
        'gemini_label': 'Polnisch',
        'spacy_model': 'pl_core_news_sm',
        'spacy_download': 'python -m spacy download pl_core_news_sm',
    },
}

# Derive spaCy model mappings from supported languages
SPACY_MODELS = {code: meta['spacy_model'] for code, meta in SUPPORTED_LANGUAGES.items()}


def normalize_language_code(lang: str) -> str:
    """Normalize Kindle language codes (e.g. 'en_US' → 'en')."""
    if not lang:
        return ''
    return lang.split('_', 1)[0].lower()


def get_language_meta(code: str) -> dict:
    """Return metadata for a supported language or raise ValueError."""
    if code not in SUPPORTED_LANGUAGES:
        supported = ', '.join(SUPPORTED_LANGUAGES.keys())
        raise ValueError(f"Unsupported language code '{code}'. Supported: {supported}")
    return SUPPORTED_LANGUAGES[code]


def format_language_pair(native_code: str, target_code: str) -> str:
    """Return canonical deck/file prefix (e.g. 'de_en')."""
    return f"{native_code}_{target_code}".lower()


def build_field_key(language_code: str, suffix: str) -> str:
    """Build structured field names like 'EN_lemma'."""
    return f"{language_code.upper()}_{suffix}"


def validate_language_configuration():
    """Ensure CONFIG languages are supported and return (native, target)."""
    native = CONFIG.get('SOURCE_LANGUAGE', 'de').lower()
    target = CONFIG.get('TARGET_LANGUAGE', 'en').lower()
    get_language_meta(native)
    get_language_meta(target)
    return native, target
