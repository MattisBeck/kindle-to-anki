"""
Configuration settings for Kindle to Anki converter
"""
CONFIG = {
    # Gemini API Key (required)
    'GEMINI_API_KEY': "", 
    
    # Paths
    'VOCAB_DB_PATH': 'put_vocab_db_here/vocab.db',  # Path to Kindle vocabulary database
    'TSV_OUTPUT_DIR': 'anki_cards/tsv_files',  # TSV files for Anki
    'APKG_OUTPUT_DIR': 'anki_cards/apkg_files',  # APKG packages for direct import
    'PROGRESS_FILE': 'anki_cards/progress.json',  # Progress tracking
    'ERROR_LOG': 'anki_cards/errors.log',  # Error log
    'TRANSLATED_CACHE': 'anki_cards/translated_cache.json',  # Cache for translated vocabulary
    
    # Batch settings (to comply with API limits: RPM 15, TPM 1,000,000, RPD 200)
    'BATCH_SIZE': 20,  # Words per batch
    'DELAY_BETWEEN_BATCHES': 4.5,  # Seconds delay between batches (for RPM 15 = ~4-5 sec)
    'MAX_RETRIES': 3,  # Number of retry attempts on API errors
    'RETRY_DELAY': 10,  # Seconds to wait before retry
    
    # Output options
    'CREATE_EN_DE_CARDS': True,  # Create English → German cards
    'CREATE_DE_EN_CARDS': True,  # Create German → English cards
    'CREATE_DE_DE_CARDS': True,  # Create German → German cards
    'SKIP_DUPLICATES': True,  # Skip duplicate vocabulary
    'SKIP_TRANSLATED': True,  # Skip already translated vocabulary
    'CREATE_APKG': True,  # Automatically create APKG packages (requires genanki)
    
    # Debugging
    'VERBOSE': True,  # Detailed output
    'DRY_RUN': False,  # If True, no API calls are made (for testing)
    'SAVE_RAW_RESPONSES': False,  # Save API responses (for debugging)
    'SAVE_RAW_INPUTS': False,  # Save API prompts (for debugging)
}

# spaCy model mappings
SPACY_MODELS = {
    'en': 'en_core_web_sm',
    'de': 'de_core_news_sm',
}
