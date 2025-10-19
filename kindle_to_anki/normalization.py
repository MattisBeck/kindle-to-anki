"""
Text normalization functions for lemmatization, book titles, and glosses
"""

import re
from typing import Optional
from collections import Counter

# Global caches for consistent naming
BOOK_TITLE_CACHE = {}
BOOK_AUTHOR_CACHE = {}
GEMINI_AUTHOR_CACHE = {}


def lemmatize_word(word: str, language: str, nlp_models=None, nlp_en=None, nlp_de=None) -> str:
    """
    Lemmatize a word using spaCy
    
    Args:
        word: Word to lemmatize
        language: 'en' or 'de'
        nlp_en: spaCy English model
        nlp_de: spaCy German model
        
    Returns:
        Lemma in lowercase (except proper nouns stay capitalized)
    """
    nlp = None

    if isinstance(nlp_models, dict):
        nlp = nlp_models.get(language)
    else:
        if language == 'en':
            nlp = nlp_en
        elif language == 'de':
            nlp = nlp_de
    
    if not nlp:
        return word.lower()  # Fallback: simple lowercase
    
    # Process the word
    doc = nlp(word)
    
    if len(doc) == 0:
        return word.lower()
    
    # For phrasal verbs or multiple words: keep all lemmas
    if len(doc) > 1:
        lemmas = [token.lemma_ for token in doc]
        result = ' '.join(lemmas)
    else:
        token = doc[0]
        result = token.lemma_
    
    # Keep proper nouns capitalized
    if doc[0].pos_ == 'PROPN':
        return result
    
    return result.lower()


def normalize_roman_numerals(text: str) -> str:
    """
    Normalize Roman numerals to uppercase
    
    Args:
        text: Text containing potential Roman numerals
        
    Returns:
        Text with normalized Roman numerals
    """
    words = text.split()
    result = []
    
    for word in words:
        # Check if word is a Roman numeral
        clean_word = word.strip(',:;!?.')
        
        if clean_word.upper() in ['I', 'II', 'III', 'IV', 'V', 'VI', 'VII', 'VIII', 'IX', 'X', 'XI', 'XII']:
            # Replace only the word itself, keep punctuation
            if word != clean_word:
                word = word.replace(clean_word, clean_word.upper())
            else:
                word = clean_word.upper()
        
        result.append(word)
    
    return ' '.join(result)


def get_author_from_gemini(book_title: str, genai, verbose: bool = False) -> Optional[str]:
    """
    Ask Gemini 3x for the author of a book and use majority vote
    
    Args:
        book_title: Normalized book title (without author)
        genai: Gemini API instance
        verbose: Enable verbose output
        
    Returns:
        Author in format "Firstname Lastname" or None if not conclusive
    """
    # Check cache
    cache_key = book_title.lower().strip()
    if cache_key in GEMINI_AUTHOR_CACHE:
        return GEMINI_AUTHOR_CACHE[cache_key]
    
    if not genai:
        return None
    
    prompt = f"""You are an expert on books and authors.

TASK: Return ONLY the full name of the author for the following book:

Book title: "{book_title}"

IMPORTANT:
- ONLY the author's name, nothing else!
- Format: "Firstname Lastname" (e.g. "Alex Hormozi", "MJ DeMarco")
- If the author is unknown, respond with "Unknown"
- No explanation, no formatting, just the name!

Author:"""

    authors = []
    
    try:
        model = genai.GenerativeModel('gemini-2.0-flash')
        
        # Ask 3 times
        for i in range(3):
            response = model.generate_content(prompt)
            author = response.text.strip()
            
            # Clean response
            author = author.replace('"', '').replace("'", '').strip()
            
            # Remove possible prefixes like "Author:" or "Autor:"
            if ':' in author:
                author = author.split(':', 1)[1].strip()
            
            authors.append(author)
            
            if verbose:
                print(f"    🤖 Gemini attempt {i+1}/3: '{author}'")
        
        # Majority vote
        counts = Counter(authors)
        most_common = counts.most_common(1)[0]
        
        # Only accept if at least 2 of 3 agree
        if most_common[1] >= 2:
            result = most_common[0]
            if result.lower() != 'unknown':
                GEMINI_AUTHOR_CACHE[cache_key] = result
                if verbose:
                    print(f"    ✅ Majority vote: '{result}' ({most_common[1]}/3)")
                return result
        
        if verbose:
            print(f"    ⚠️  No consensus: {authors}")
        
    except Exception as e:
        if verbose:
            print(f"    ❌ Gemini error: {e}")
    
    return None


def normalize_book_title(raw_title: str, author_from_db: Optional[str] = None, 
                        genai_instance=None, verbose: bool = False) -> str:
    """
    Normalize book title for consistent formatting - DETERMINISTIC without LLM
    Uses cache for consistent Title Case formatting
    
    Format: "Main Title: Subtitle — Author"
    
    Author extraction (priority):
    1. FIRST CHOICE: author_from_db (from vocab.db BOOK_INFO.authors)
    2. SECOND CHOICE: Parse from title (if -- or — present)
    3. LAST CHOICE: Generate from Gemini (3-fold majority vote)
    
    Generic rules (work for ALL books):
    - Title Case with minor words (a, an, the, etc.)
    - Normalize Roman numerals (Iii -> III)
    - Fix underscores/commas
    - Em-Dash (—) instead of "--"
    - Author format: "Firstname Lastname"
    
    Args:
        raw_title: Raw book title from database or API
        author_from_db: Author directly from BOOK_INFO.authors (optional)
        genai_instance: Gemini API instance for author generation (optional)
        verbose: Enable verbose output
        
    Returns:
        Normalized title in consistent format
    """
    if not raw_title or raw_title == "Unknown":
        return raw_title
    
    # Remove leading/trailing whitespace
    title = raw_title.strip()
    
    # Normalize for comparison (lowercase + unify punctuation)
    normalized_key = title.lower().strip()
    cache_key = normalized_key
    for char in [':', '-', '_', ',', '–', '—']:
        cache_key = cache_key.replace(char, ' ')
    while '  ' in cache_key:
        cache_key = cache_key.replace('  ', ' ')
    cache_key = cache_key.strip()
    
    # Check if similar title already in cache
    if cache_key in BOOK_TITLE_CACHE:
        return BOOK_TITLE_CACHE[cache_key]
    
    # 1) Determine author (Priority: DB → Title → Cache)
    author = None
    title_had_author = False
    
    # FIRST CHOICE: Author from database
    if author_from_db and author_from_db != "Unknown":
        author = author_from_db.strip()
        # Remove author from title if present (DB has priority!)
        if ' -- ' in title:
            title = title.rsplit(' -- ', 1)[0].strip()
            title_had_author = True
        elif ' — ' in title:
            title = title.rsplit(' — ', 1)[0].strip()
            title_had_author = True
        elif ' - ' in title:
            title = title.rsplit(' - ', 1)[0].strip()
            title_had_author = True
    
    # SECOND CHOICE: Extract author from title (only if not from DB)
    if not author and not title_had_author:
        if ' -- ' in title:
            parts = title.split(' -- ')
            if len(parts) >= 2:
                title = parts[0].strip()
                author = parts[1].strip()
            else:
                parts = title.rsplit(' -- ', 1)
                title, author = parts[0].strip(), parts[1].strip()
        elif ' — ' in title:
            parts = title.rsplit(' — ', 1)
            title, author = parts[0].strip(), parts[1].strip()
        elif ' - ' in title:
            parts = title.rsplit(' - ', 1)
            title, author = parts[0].strip(), parts[1].strip()
    
    # THIRD CHOICE: Generate from Gemini (if available)
    if not author and genai_instance:
        temp_title = title.replace('_ ', ': ').replace('_', ': ')
        author = get_author_from_gemini(temp_title, genai_instance, verbose)
        if author and verbose:
            print(f"    🤖 Gemini generated author: '{author}'")
    
    # 2) Normalize author format: "Lastname, Firstname" -> "Firstname Lastname"
    if author and ', ' in author:
        parts = author.split(', ', 1)
        author = f"{parts[1]} {parts[0]}"
    
    # 3) Format smoothing and metadata cleanup
    title = title.replace('_ ', ': ')
    title = title.replace('_', ': ')
    title = title.replace(', Episode', ': Episode')
    
    # Remove incomplete parentheses
    if '(' in title and ')' not in title:
        title = title.split('(')[0].strip()
    
    # Remove excess metadata
    if ' -- ' in title and title_had_author:
        title = title.split(' -- ')[0].strip()
    
    # 4) FIRST: Normalize Roman numerals (BEFORE Title Case!)
    title = normalize_roman_numerals(title)
    if author:
        author = normalize_roman_numerals(author)
    
    # 5) Apply Title Case (BEFORE special rules)
    minor_words = {'a', 'an', 'and', 'as', 'at', 'but', 'by', 'for', 'in', 'of', 'on', 'or', 'the', 'to', 'with'}
    german_minor = {'der', 'die', 'das', 'den', 'dem', 'des', 'ein', 'eine', 'einen', 'einem', 'eines', 
                    'und', 'oder', 'aber', 'für', 'von', 'mit', 'zu', 'im', 'am', 'durch', 'über'}
    minor_words = minor_words | german_minor
    
    words = title.split()
    title_case_words = []
    
    for i, word in enumerate(words):
        word_base = word.rstrip(':,;.!?')
        if word_base.upper() in ['I', 'II', 'III', 'IV', 'V', 'VI', 'VII', 'VIII', 'IX', 'X', 'XI', 'XII']:
            title_case_words.append(word_base.upper() + word[len(word_base):])
        elif i == 0 or i == len(words) - 1:
            title_case_words.append(word.capitalize())
        elif i > 0 and ':' in words[i-1]:
            title_case_words.append(word.capitalize())
        elif word.lower() in minor_words and not any(c.isupper() for c in word):
            title_case_words.append(word.lower())
        else:
            title_case_words.append(word.capitalize())
    
    title_case_title = ' '.join(title_case_words)
    
    # 6) Combine with author (use Em-Dash —)
    if author:
        author_in_title = False
        title_lower = title_case_title.lower()
        author_lower = author.lower()
        
        if author_lower in title_lower:
            author_in_title = True
        elif ' ' in author:
            last_name = author.split()[-1].lower()
            if last_name in title_lower:
                author_in_title = True
        
        if not author_in_title:
            final_title = f"{title_case_title} — {author}"
            title_key = title_case_title.lower().strip()
            BOOK_AUTHOR_CACHE[title_key] = author
        else:
            final_title = title_case_title
            if verbose:
                print(f"    ℹ️  Author '{author}' already in title")
    else:
        final_title = title_case_title
    
    # Save in cache
    BOOK_TITLE_CACHE[cache_key] = final_title
    
    return final_title


def normalize_de_gloss(gloss: str) -> str:
    """
    Normalize German translation - ONLY clear cases
    
    Rules:
    - Completely UPPERCASE becomes Mixed Case (smart)
    - Verbs, adjectives, adverbs stay lowercase
    - Nouns capitalized
    - Ambiguous cases stay unchanged
    
    Examples:
    - "KUMMER, LEID" -> "Kummer, Leid" (nouns)
    - "zittern" -> "zittern" (stays lowercase - verb)
    - "HEFTIG" -> "heftig" (adjective)
    - "Furcht" -> "Furcht" (stays - already correct)
    
    Args:
        gloss: German translation string
        
    Returns:
        Normalized German translation
    """
    if not gloss:
        return gloss
    
    # Typical adjective endings
    adjective_endings = [
        'bar', 'haft', 'ig', 'isch', 'lich', 'los', 'sam', 'voll',
        'end', 'fach', 'arm', 'reich', 'mäßig', 'weise'
    ]
    
    # Typical noun endings
    noun_endings = [
        'heit', 'keit', 'schaft', 'ung', 'tum', 'nis', 'chen', 'lein',
        'ment', 'ion', 'ität', 'ismus', 'anz', 'enz'
    ]
    
    # Typical verb endings (infinitive)
    verb_endings = ['en', 'ern', 'eln']
    
    # Split by comma
    parts = [p.strip() for p in gloss.split(',')]
    
    normalized_parts = []
    for part in parts:
        # If completely UPPERCASE -> needs decision
        if part.isupper() and len(part) > 1:
            lower_part = part.lower()
            
            is_noun = any(lower_part.endswith(ending) for ending in noun_endings)
            is_adjective = any(lower_part.endswith(ending) for ending in adjective_endings)
            is_verb = any(lower_part.endswith(ending) for ending in verb_endings)
            
            if is_adjective or is_verb:
                part = lower_part
            elif is_noun or (not is_adjective and not is_verb):
                part = part.capitalize()
        
        normalized_parts.append(part)
    
    return ', '.join(normalized_parts)


def load_book_titles_from_cache(cache: dict, verbose: bool = False):
    """
    Load all book titles from cache into RAM for consistent formatting
    
    Args:
        cache: Translated cache dictionary
        verbose: Enable verbose output
    """
    global BOOK_TITLE_CACHE
    
    for language_cards in cache.get('languages', {}).values():
        for card in language_cards.values():
            book = card.get('Book', '')
            if book and book != "Unknown":
                normalized_key = book.lower().strip()
                if normalized_key not in BOOK_TITLE_CACHE:
                    BOOK_TITLE_CACHE[normalized_key] = book
    
    if verbose and BOOK_TITLE_CACHE:
        print(f"  📚 {len(BOOK_TITLE_CACHE)} unique book titles loaded into RAM")
