"""
Helper functions for configuration validation and language handling
"""

from .config import CONFIG, SUPPORTED_LANGUAGES


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


def validate_api_key():
    """Validate that GEMINI_API_KEY is set and has correct format."""
    api_key = CONFIG.get('GEMINI_API_KEY', '').strip()
    
    if not api_key:
        raise ValueError(
            "❌ GEMINI_API_KEY is empty!\n"
            "   Please add your API key in kindle_to_anki/config.py\n"
            "   Get a free key at: https://aistudio.google.com/apikey"
        )
    
    if not api_key.startswith('AIza'):
        raise ValueError(
            "❌ Invalid GEMINI_API_KEY format!\n"
            "   Google Gemini API keys start with 'AIza'\n"
            f"   Your key starts with: '{api_key[:10]}...'\n"
            "   Get a valid key at: https://aistudio.google.com/apikey"
        )
    
    return api_key
