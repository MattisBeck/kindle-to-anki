#!/usr/bin/env python3
"""
Kindle to Anki Converter
Converts Kindle vocabulary database to Anki flashcards using Gemini 2.0 Flash API
"""

import sqlite3
import json
import time
import sys
import re
from pathlib import Path
from typing import List, Dict, Tuple
import os

# NLP für Lemmatisierung
try:
    import spacy
    SPACY_AVAILABLE = True
    # Lade spaCy Modelle (werden beim ersten Aufruf geladen)
    try:
        nlp_en = spacy.load("en_core_web_sm")
    except OSError:
        # Warnung nur beim Start (CONFIG noch nicht verfügbar)
        print("⚠️  spaCy Modell 'en_core_web_sm' nicht gefunden!")
        print("   Installiere mit: python -m spacy download en_core_web_sm")
        nlp_en = None
    
    try:
        nlp_de = spacy.load("de_core_news_sm")
    except OSError:
        # Warnung nur beim Start (CONFIG noch nicht verfügbar)
        print("⚠️  spaCy Modell 'de_core_news_sm' nicht gefunden!")
        print("   Installiere mit: python -m spacy download de_core_news_sm")
        nlp_de = None
except ImportError:
    # Warnung nur wenn VERBOSE (CONFIG wird später geladen, also immer anzeigen)
    print("⚠️  spaCy nicht installiert! Lemmatisierung wird von Gemini übernommen.")
    print("   Installiere mit: pip install spacy")
    SPACY_AVAILABLE = False
    nlp_en = None
    nlp_de = None

# ============================================================================
# CONFIGURATION - Bitte hier die Variablen anpassen
# ============================================================================

CONFIG = {
    # Gemini API Key (erforderlich)
    'GEMINI_API_KEY': 'YOUR_GEMINI_API_KEY',  # Trage hier deinen API-Key ein
    
    # Pfade
    'VOCAB_DB_PATH': 'vocab.db',
    'TSV_OUTPUT_DIR': 'anki_cards/tsv_files',  # TSV-Dateien für Anki
    'APKG_OUTPUT_DIR': 'anki_cards/apkg_files',  # APKG-Pakete für direkten Import
    'PROGRESS_FILE': 'anki_cards/progress.json',  # Fortschritt speichern
    'ERROR_LOG': 'anki_cards/errors.log',  # Fehler-Log
    'TRANSLATED_CACHE': 'anki_cards/translated_cache.json',  # Cache für bereits übersetzte Vokabeln
    
    # Batch-Einstellungen (um API-Limits einzuhalten: RPM 15, TPM 1.000.000, RPD 200)
    'BATCH_SIZE': 20,  # Niedrigere Batch-Größe für mehr Qualität
    'DELAY_BETWEEN_BATCHES': 4.5,  # Sekunden Pause zwischen Batches (für RPM 15 = ~4-5 Sek.)
    'MAX_RETRIES': 3,  # Anzahl Wiederholungsversuche bei API-Fehlern
    'RETRY_DELAY': 10,  # Sekunden Wartezeit vor Wiederholung
    
    # Ausgabeoptionen
    'CREATE_EN_DE_CARDS': True,  # Englisch → Deutsch Karten erstellen
    'CREATE_DE_EN_CARDS': True,  # Deutsch → Englisch Karten erstellen
    'CREATE_DE_DE_CARDS': True,  # Deutsch → Deutsch Karten erstellen
    'SKIP_DUPLICATES': True,  # Doppelte Vokabeln überspringen
    'SKIP_TRANSLATED': True,  # Bereits übersetzte Vokabeln überspringen
    'CREATE_APKG': True,  # APKG-Pakete automatisch erstellen (benötigt genanki)
    
    # Debugging
    'VERBOSE': False,  # Detaillierte Ausgabe
    'DRY_RUN': False,  # Wenn True, werden keine API-Calls gemacht (zum Testen)
    'SAVE_RAW_RESPONSES': True,  # API-Antworten speichern (für Debugging)
    'SAVE_RAW_INPUTS': True,  # API-Prompts speichern (für Debugging)
}

# ============================================================================
# Helper Functions
# ============================================================================

# Global: Book Title Cache für einheitliche Schreibweise
BOOK_TITLE_CACHE = {}

# Global: Autoren-Cache (Buch → Autor Mapping)
BOOK_AUTHOR_CACHE = {}

# Global: Gemini-generierte Autoren (um nicht mehrfach zu fragen)
GEMINI_AUTHOR_CACHE = {}

def lemmatize_word(word: str, language: str) -> str:
    """
    Lemmatisiert ein Wort mit spaCy.
    
    Args:
        word: Das zu lemmatisierende Wort
        language: 'en' oder 'de'
    
    Returns:
        Lemma in Kleinbuchstaben (außer Eigennamen bleiben groß)
    """
    if not SPACY_AVAILABLE:
        return word.lower()  # Fallback: einfach lowercase
    
    nlp = nlp_en if language == 'en' else nlp_de
    
    if not nlp:
        return word.lower()  # Fallback wenn Modell nicht geladen
    
    # Verarbeite das Wort
    doc = nlp(word)
    
    if len(doc) == 0:
        return word.lower()
    
    # Bei Phrasal Verbs oder mehreren Wörtern: Behalte alle Lemmata
    if len(doc) > 1:
        # Phrasal Verbs: "picked up" -> "pick up"
        lemmas = [token.lemma_ for token in doc]
        result = ' '.join(lemmas)
    else:
        # Einzelnes Wort
        token = doc[0]
        result = token.lemma_
    
    # Eigennamen behalten Großschreibung
    if doc[0].pos_ == 'PROPN':
        return result
    
    return result.lower()

def normalize_roman_numerals(text: str) -> str:
    """Normalisiert römische Zahlen zu Großbuchstaben."""
    # Wort für Wort durchgehen
    words = text.split()
    result = []
    
    for word in words:
        # Prüfe ob das Wort eine römische Zahl ist
        # Entferne Satzzeichen für den Test
        clean_word = word.strip(',:;!?.')
        
        if clean_word.upper() in ['I', 'II', 'III', 'IV', 'V', 'VI', 'VII', 'VIII', 'IX', 'X', 'XI', 'XII']:
            # Ersetze nur das eigentliche Wort, behalte Satzzeichen
            if word != clean_word:
                # Hat Satzzeichen
                word = word.replace(clean_word, clean_word.upper())
            else:
                word = clean_word.upper()
        
        result.append(word)
    
    return ' '.join(result)

def get_author_from_gemini(book_title: str, genai) -> str:
    """
    Fragt Gemini 3x nach dem Autor eines Buches und nimmt Mehrheitsentscheid.
    
    Args:
        book_title: Normalisierter Buchtitel (ohne Autor)
        genai: Gemini API Instanz
        
    Returns:
        Autor im Format "Vorname Nachname" oder None falls nicht eindeutig
    """
    # Prüfe Cache
    cache_key = book_title.lower().strip()
    if cache_key in GEMINI_AUTHOR_CACHE:
        return GEMINI_AUTHOR_CACHE[cache_key]
    
    if not genai:
        return None
    
    prompt = f"""Du bist ein Experte für Bücher und Autoren.

AUFGABE: Gib NUR den vollen Namen des Autors für folgendes Buch zurück:

Buchtitel: "{book_title}"

WICHTIG:
- NUR der Autorenname, nichts anderes!
- Format: "Vorname Nachname" (z.B. "Alex Hormozi", "MJ DeMarco")
- Falls der Autor unbekannt ist, antworte mit "Unknown"
- Keine Erklärung, keine Formatierung, nur der Name!

Autor:"""

    authors = []
    
    try:
        model = genai.GenerativeModel('gemini-2.0-flash')
        
        # 3x abfragen
        for i in range(3):
            response = model.generate_content(prompt)
            author = response.text.strip()
            
            # Bereinige Antwort
            author = author.replace('"', '').replace("'", '').strip()
            
            # Entferne mögliche Präfixe wie "Autor:" oder "Author:"
            if ':' in author:
                author = author.split(':', 1)[1].strip()
            
            authors.append(author)
            
            if CONFIG['VERBOSE']:
                print(f"    🤖 Gemini Versuch {i+1}/3: '{author}'")
        
        # Mehrheitsentscheid
        from collections import Counter
        counts = Counter(authors)
        most_common = counts.most_common(1)[0]
        
        # Nur akzeptieren wenn mindestens 2 von 3 übereinstimmen
        if most_common[1] >= 2:
            result = most_common[0]
            if result.lower() != 'unknown':
                GEMINI_AUTHOR_CACHE[cache_key] = result
                if CONFIG['VERBOSE']:
                    print(f"    ✅ Mehrheitsentscheid: '{result}' ({most_common[1]}/3)")
                return result
        
        if CONFIG['VERBOSE']:
            print(f"    ⚠️  Keine Einigkeit: {authors}")
        
    except Exception as e:
        if CONFIG['VERBOSE']:
            print(f"    ❌ Gemini-Fehler: {e}")
    
    return None

def normalize_book_title(raw_title: str, author_from_db: str = None, genai_instance = None) -> str:
    """
    Normalisiert Buchtitel für einheitliche Schreibweise - DETERMINISTISCH ohne LLM.
    Verwendet Cache für konsistente Title Case Schreibweise.
    
    Format: "Haupttitel: Untertitel — Autor"
    
    Autoren-Extraktion (Priorität):
    1. ERSTE WAHL: author_from_db (aus vocab.db BOOK_INFO.authors)
    2. ZWEITE WAHL: Aus dem Titel parsen (falls -- oder — vorhanden)
    3. LETZTE WAHL: Von Gemini generieren (3-fach Mehrheitsentscheid)
    
    Generische Regeln (funktionieren für ALLE Bücher):
    - Title Case mit minor words (a, an, the, etc.)
    - Römische Zahlen normalisieren (Iii -> III)
    - Unterstriche/Kommas korrigieren
    - Em-Dash (—) statt "--"
    - Autorformat: "Vorname Nachname"
    
    Args:
        raw_title: Roher Buchtitel aus Datenbank oder API
        author_from_db: Autor direkt aus BOOK_INFO.authors (optional)
        genai_instance: Gemini API Instanz für Autoren-Generierung (optional)
    Returns:
        Normalisierter Titel in einheitlichem Format
    """
    if not raw_title or raw_title == "Unknown":
        return raw_title
    
    # Entferne führende/nachfolgende Leerzeichen
    title = raw_title.strip()
    
    # Normalisiere für Vergleich (lowercase + Interpunktion vereinheitlichen)
    # Damit "Episode III-" und "Episode III:" zum selben Cache-Key führen
    normalized_key = title.lower().strip()
    # Ersetze verschiedene Trennzeichen für konsistenten Vergleich
    cache_key = normalized_key
    for char in [':', '-', '_', ',', '–', '—']:
        cache_key = cache_key.replace(char, ' ')
    # Mehrfache Leerzeichen entfernen
    while '  ' in cache_key:
        cache_key = cache_key.replace('  ', ' ')
    cache_key = cache_key.strip()
    
    # Prüfe ob ähnlicher Titel bereits im Cache ist
    if cache_key in BOOK_TITLE_CACHE:
        return BOOK_TITLE_CACHE[cache_key]
    
    # 1) Autor bestimmen (Priorität: DB → Titel → Cache)
    author = None
    title_had_author = False  # Flag ob Titel bereits Autor enthielt
    
    # ERSTE WAHL: Autor aus Datenbank
    if author_from_db and author_from_db != "Unknown":
        author = author_from_db.strip()
        # Entferne Autor aus Titel falls vorhanden (DB hat Priorität!)
        if ' -- ' in title:
            title = title.rsplit(' -- ', 1)[0].strip()
            title_had_author = True
        elif ' — ' in title:
            title = title.rsplit(' — ', 1)[0].strip()
            title_had_author = True
        elif ' - ' in title:
            title = title.rsplit(' - ', 1)[0].strip()
            title_had_author = True
    
    # ZWEITE WAHL: Autor aus Titel extrahieren (nur wenn nicht aus DB)
    if not author and not title_had_author:
        if ' -- ' in title:
            # Bei Metadata: Nimm ERSTEN Teil nach Haupttitel, nicht letzten!
            # Format: "Titel -- Autor -- Jahr -- Verlag" → Autor ist nach 1. "--"
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
        elif ' - ' in title:  # Single dash (1984 - George Orwell)
            parts = title.rsplit(' - ', 1)
            title, author = parts[0].strip(), parts[1].strip()
    
    # DRITTE WAHL: Von Gemini generieren (falls verfügbar)
    if not author and genai_instance:
        # Normalisiere Titel erstmal für Gemini-Anfrage
        temp_title = title.replace('_ ', ': ').replace('_', ': ')
        author = get_author_from_gemini(temp_title, genai_instance)
        if author and CONFIG['VERBOSE']:
            print(f"    🤖 Gemini generierter Autor: '{author}'")
    
    # 2) Autorformat normalisieren: "Nachname, Vorname" -> "Vorname Nachname"
    if author and ', ' in author:
        parts = author.split(', ', 1)
        author = f"{parts[1]} {parts[0]}"
    
    # 3) Formatglättung und Metadaten-Bereinigung
    title = title.replace('_ ', ': ')
    title = title.replace('_', ': ')
    title = title.replace(', Episode', ': Episode')
    
    # Entferne unvollständige Klammern: Wenn '(' ohne ')', schneide ab
    if '(' in title and ')' not in title:
        title = title.split('(')[0].strip()
    
    # Entferne überschüssige Metadaten (Anna's Archive, ISBN, etc.)
    # Format: "Titel -- Metadaten -- weitere Metadaten"
    # Wir wollen nur den ersten Teil (den eigentlichen Titel)
    if ' -- ' in title and title_had_author:
        # Falls wir schon Autor aus DB haben, alles nach dem ersten -- ist Müll
        title = title.split(' -- ')[0].strip()
    
    # 4) ZUERST: Normalisiere römische Zahlen (BEVOR Title Case!)
    title = normalize_roman_numerals(title)
    if author:
        author = normalize_roman_numerals(author)
    
    # 5) Title Case anwenden (BEVOR Spezialregeln)
    minor_words = {'a', 'an', 'and', 'as', 'at', 'but', 'by', 'for', 'in', 'of', 'on', 'or', 'the', 'to', 'with'}
    # Deutsche Artikel und Präpositionen auch klein halten
    german_minor = {'der', 'die', 'das', 'den', 'dem', 'des', 'ein', 'eine', 'einen', 'einem', 'eines', 
                    'und', 'oder', 'aber', 'für', 'von', 'mit', 'zu', 'im', 'am', 'durch', 'über'}
    minor_words = minor_words | german_minor
    
    words = title.split()
    title_case_words = []
    
    for i, word in enumerate(words):
        # Römische Zahlen NICHT ändern (bereits normalisiert) - auch mit angehängten Zeichen wie ':'
        word_base = word.rstrip(':,;.!?')
        if word_base.upper() in ['I', 'II', 'III', 'IV', 'V', 'VI', 'VII', 'VIII', 'IX', 'X', 'XI', 'XII']:
            title_case_words.append(word_base.upper() + word[len(word_base):])
        # Erstes und letztes Wort immer groß
        elif i == 0 or i == len(words) - 1:
            title_case_words.append(word.capitalize())
        # Nach Doppelpunkt groß
        elif i > 0 and ':' in words[i-1]:
            title_case_words.append(word.capitalize())
        # Minor words klein
        elif word.lower() in minor_words and not any(c.isupper() for c in word):
            title_case_words.append(word.lower())
        # Rest: Capitalize
        else:
            title_case_words.append(word.capitalize())
    
    title_case_title = ' '.join(title_case_words)
    
    # 6) Kombiniere mit Autor (verwende Em-Dash —)
    if author:
        # Prüfe ob Autor bereits im Titel vorkommt (z.B. "1984 - George Orwell")
        author_in_title = False
        title_lower = title_case_title.lower()
        author_lower = author.lower()
        
        # Suche nach Autor-Varianten im Titel
        if author_lower in title_lower:
            author_in_title = True
        # Auch Nachname alleine checken
        elif ' ' in author:
            last_name = author.split()[-1].lower()
            if last_name in title_lower:
                author_in_title = True
        
        if not author_in_title:
            final_title = f"{title_case_title} — {author}"
            # Speichere Autor im Cache für dieses Buch
            title_key = title_case_title.lower().strip()
            BOOK_AUTHOR_CACHE[title_key] = author
        else:
            # Autor ist bereits im Titel - nicht nochmal anhängen
            final_title = title_case_title
            if CONFIG['VERBOSE']:
                print(f"    ℹ️  Autor '{author}' bereits im Titel enthalten")
    else:
        # Kein Autor verfügbar - Titel ohne Autor (Gemini kann später ergänzen)
        final_title = title_case_title
    
    # Im Cache speichern (mit normalisiertem Key)
    BOOK_TITLE_CACHE[cache_key] = final_title
    
    return final_title

def load_book_titles_from_cache(cache: Dict):
    """
    Lädt alle Buchtitel aus dem Cache in den RAM für konsistente Schreibweise.
    """
    global BOOK_TITLE_CACHE
    
    # EN words
    for card in cache.get('en_words', {}).values():
        book = card.get('Book', '')
        if book and book != "Unknown":
            normalized_key = book.lower().strip()
            if normalized_key not in BOOK_TITLE_CACHE:
                BOOK_TITLE_CACHE[normalized_key] = book
    
    # DE words
    for card in cache.get('de_words', {}).values():
        book = card.get('Book', '')
        if book and book != "Unknown":
            normalized_key = book.lower().strip()
            if normalized_key not in BOOK_TITLE_CACHE:
                BOOK_TITLE_CACHE[normalized_key] = book
    
    if CONFIG['VERBOSE'] and BOOK_TITLE_CACHE:
        print(f"  📚 {len(BOOK_TITLE_CACHE)} einzigartige Buchtitel in RAM geladen")

def log_error(message: str, error: Exception = None):
    """Schreibt Fehler in Log-Datei."""
    output_dir = Path(CONFIG['TSV_OUTPUT_DIR']).parent  # anki_cards/
    output_dir.mkdir(parents=True, exist_ok=True)
    
    with open(CONFIG['ERROR_LOG'], 'a', encoding='utf-8') as f:
        timestamp = time.strftime('%Y-%m-%d %H:%M:%S')
        f.write(f"[{timestamp}] {message}\n")
        if error:
            f.write(f"  Error: {str(error)}\n")
        f.write("\n")

def save_progress(processed_batches: Dict):
    """Speichert Fortschritt."""
    output_dir = Path(CONFIG['TSV_OUTPUT_DIR']).parent  # anki_cards/
    output_dir.mkdir(parents=True, exist_ok=True)
    
    with open(CONFIG['PROGRESS_FILE'], 'w', encoding='utf-8') as f:
        json.dump(processed_batches, f, indent=2)

def load_progress() -> Dict:
    """Lädt gespeicherten Fortschritt."""
    if Path(CONFIG['PROGRESS_FILE']).exists():
        with open(CONFIG['PROGRESS_FILE'], 'r', encoding='utf-8') as f:
            return json.load(f)
    return {'en_batches_done': 0, 'de_batches_done': 0}

def load_translated_cache() -> Dict:
    """Lädt Cache mit bereits übersetzten Vokabeln."""
    if Path(CONFIG['TRANSLATED_CACHE']).exists():
        try:
            with open(CONFIG['TRANSLATED_CACHE'], 'r', encoding='utf-8') as f:
                content = f.read().strip()
                if not content:  # Leere Datei
                    return {'en_words': {}, 'de_words': {}}
                return json.loads(content)
        except json.JSONDecodeError:
            print("⚠️  Cache-Datei beschädigt, erstelle neuen Cache...")
            return {'en_words': {}, 'de_words': {}}
    return {'en_words': {}, 'de_words': {}}

def save_translated_cache(cache: Dict):
    """Speichert Cache mit übersetzten Vokabeln."""
    output_dir = Path(CONFIG['TSV_OUTPUT_DIR']).parent  # anki_cards/
    output_dir.mkdir(parents=True, exist_ok=True)
    
    with open(CONFIG['TRANSLATED_CACHE'], 'w', encoding='utf-8') as f:
        json.dump(cache, f, indent=2, ensure_ascii=False)

def is_word_translated(word_id: str, language: str, cache: Dict) -> bool:
    """Prüft, ob eine Vokabel bereits übersetzt wurde."""
    if language == 'en':
        return word_id in cache.get('en_words', {})
    else:
        return word_id in cache.get('de_words', {})

def add_to_cache(cards: List[Dict], words: List[Dict], language: str, cache: Dict):
    """
    Fügt übersetzte Vokabeln zum Cache hinzu.
    Matcht jede Karte mit dem passenden Wort aus dem Batch anhand des Original_word-Felds.
    Prüft auf Duplikate basierend auf Lemma (case-insensitive).
    
    WICHTIG: Word-IDs werden aus Lemma generiert, NICHT aus Original_word!
    Das stellt sicher, dass "Pity" und "pity" dieselbe ID "en:pity" bekommen.
    """
    cache_key = 'en_words' if language == 'en' else 'de_words'
    lemma_field = 'EN_lemma' if language == 'en' else 'DE_lemma'
    
    # Erstelle Mapping: normalisiertes Original_word -> word dict (für Metadaten)
    original_word_to_word = {}
    for word in words:
        normalized = word['word'].lower().strip()
        original_word_to_word[normalized] = word
    
    # Erstelle Lemma-Index für Duplikaterkennung
    existing_lemmas = {}
    for word_id, card in cache.get(cache_key, {}).items():
        lemma = card.get(lemma_field, '').lower().strip()
        if lemma:
            existing_lemmas[lemma] = word_id
    
    # Matche jede Karte mit dem passenden Wort
    matched_count = 0
    unmatched_cards = []
    skipped_duplicates = 0
    
    for card in cards:
        # Hole das Original_word aus der Karte
        original_word = card.get('Original_word', '').lower().strip()
        
        if not original_word:
            unmatched_cards.append("(Karte ohne Original_word)")
            continue
        
        # Hole Lemma aus der Karte
        lemma = card.get(lemma_field, '').lower().strip()
        
        if not lemma:
            unmatched_cards.append(f"{original_word} (kein Lemma)")
            continue
        
        # Prüfe auf Duplikat basierend auf Lemma
        if lemma in existing_lemmas:
            # Duplikat gefunden - überspringe
            skipped_duplicates += 1
            if CONFIG['VERBOSE']:
                print(f"    ⚠️  Duplikat übersprungen: '{lemma}' (bereits als {existing_lemmas[lemma]} vorhanden)")
            continue
        
        # Hole word dict für Metadaten (Book, Author)
        word_dict = original_word_to_word.get(original_word)
        
        if word_dict:
            # Füge Book-Feld aus Metadaten hinzu (normalisiert)
            raw_book = word_dict.get('book', 'Unknown')
            author_from_db = word_dict.get('authors', 'Unknown')
            normalized_book = normalize_book_title(raw_book, author_from_db, None)
            card['Book'] = normalized_book
        else:
            card['Book'] = 'Unknown'
        
        # Generiere Word-ID aus Lemma (nicht aus Original_word!)
        # Das stellt sicher: "en:Pity" wird zu "en:pity"
        prefix = 'en' if language == 'en' else 'de'
        word_id = f"{prefix}:{lemma}"
        
        # Kein Duplikat - hinzufügen
        cache[cache_key][word_id] = card
        existing_lemmas[lemma] = word_id
        matched_count += 1
    
    if CONFIG['VERBOSE']:
        print(f"\n   ✓ {matched_count} Karten erfolgreich zugeordnet")
        if skipped_duplicates > 0:
            print(f"   ⚠️  {skipped_duplicates} Duplikate übersprungen (bereits im Cache)")
        if unmatched_cards:
            print(f"   ⚠️  {len(unmatched_cards)} Karten ohne Zuordnung: {', '.join(unmatched_cards)}")


def normalize_de_gloss(gloss: str) -> str:
    """
    Normalisiert deutsche Übersetzung - NUR eindeutige Fälle.
    
    Regeln:
    - Komplett GROSSGESCHRIEBEN wird zu Mixed Case (smart)
    - Verben, Adjektive, Adverbien bleiben klein
    - Substantive groß
    - Zweifelsfälle bleiben unverändert
    
    Beispiele:
    - "KUMMER, LEID" -> "Kummer, Leid" (Substantive)
    - "zittern" -> "zittern" (bleibt klein - Verb)
    - "HEFTIG" -> "heftig" (Adjektiv)
    - "Furcht" -> "Furcht" (bleibt - schon richtig)
    """
    if not gloss:
        return gloss
    
    # Liste typischer Adjektiv-Endungen (eindeutig)
    adjective_endings = [
        'bar', 'haft', 'ig', 'isch', 'lich', 'los', 'sam', 'voll',
        'end', 'fach', 'arm', 'reich', 'mäßig', 'weise'
    ]
    
    # Liste typischer Substantiv-Endungen (eindeutig)
    noun_endings = [
        'heit', 'keit', 'schaft', 'ung', 'tum', 'nis', 'chen', 'lein',
        'ment', 'ion', 'ität', 'ismus', 'anz', 'enz'
    ]
    
    # Liste typischer Verb-Endungen (Infinitiv)
    verb_endings = ['en', 'ern', 'eln']
    
    # Teile bei Komma
    parts = [p.strip() for p in gloss.split(',')]
    
    normalized_parts = []
    for part in parts:
        # Wenn komplett GROSS -> muss entschieden werden
        if part.isupper() and len(part) > 1:
            lower_part = part.lower()
            
            # Prüfe auf eindeutige Substantiv-Endung
            is_noun = any(lower_part.endswith(ending) for ending in noun_endings)
            
            # Prüfe auf eindeutige Adjektiv-Endung
            is_adjective = any(lower_part.endswith(ending) for ending in adjective_endings)
            
            # Prüfe auf Verb-Endung
            is_verb = any(lower_part.endswith(ending) for ending in verb_endings)
            
            if is_adjective or is_verb:
                # Adjektiv/Verb -> klein
                part = lower_part
            elif is_noun or (not is_adjective and not is_verb):
                # Substantiv ODER unbekannt -> Capitalize (sicherer)
                part = part.capitalize()
        
        # Alle anderen Fälle: NICHT ändern (zu unsicher)
        normalized_parts.append(part)
    
    return ', '.join(normalized_parts)

def validate_card(card: Dict, language: str) -> Tuple[bool, str]:
    """Validiert, ob eine Karte alle erforderlichen Felder hat."""
    # Original_word ist für beide Sprachen erforderlich
    if 'Original_word' not in card or not card['Original_word']:
        return False, "Fehlendes Feld: Original_word"
    
    if language == 'en':
        required = ['EN_lemma', 'EN_definition', 'DE_gloss', 'Context_HTML']
        for field in required:
            if field not in card or not card[field]:
                return False, f"Fehlendes Feld: {field}"
        
        # Normalisiere DE_gloss
        card['DE_gloss'] = normalize_de_gloss(card['DE_gloss'])
        
        # Normalisiere Book (Author ist bereits im BOOK_AUTHOR_CACHE wenn verfügbar)
        if 'Book' in card:
            card['Book'] = normalize_book_title(card['Book'])
    else:  # de
        required = ['DE_lemma', 'DE_definition', 'Context_HTML']
        for field in required:
            if field not in card or not card[field]:
                return False, f"Fehlendes Feld: {field}"
        
        # Normalisiere Book (Author ist bereits im BOOK_AUTHOR_CACHE wenn verfügbar)
        if 'Book' in card:
            card['Book'] = normalize_book_title(card['Book'])
    
    # Quality Check: Warnung bei leeren Notes (aber nicht blockieren)
    if CONFIG['VERBOSE'] and card.get('Notes') == '':
        lemma = card.get('EN_lemma' if language == 'en' else 'DE_lemma', 'unknown')
        print(f"    ℹ️  Keine Notes für: {lemma}")
    
    return True, "OK"

def remove_duplicates(cards: List[Dict], language: str) -> List[Dict]:
    """Entfernt doppelte Karten basierend auf Lemma."""
    seen = set()
    unique_cards = []
    
    lemma_field = 'EN_lemma' if language == 'en' else 'DE_lemma'
    
    for card in cards:
        lemma = card.get(lemma_field, '').lower().strip()
        if lemma and lemma not in seen:
            seen.add(lemma)
            unique_cards.append(card)
        elif CONFIG['VERBOSE']:
            print(f"    ⚠️  Duplikat übersprungen: {lemma}")
    
    return unique_cards

# ============================================================================
# Datenbank-Funktionen
# ============================================================================

def connect_to_db(db_path: str) -> sqlite3.Connection:
    """Verbindet sich mit der Kindle Vocab-Datenbank."""
    if not Path(db_path).exists():
        print(f"❌ Fehler: Datenbank '{db_path}' nicht gefunden!")
        sys.exit(1)
    return sqlite3.connect(db_path)

def get_vocabulary_data(conn: sqlite3.Connection) -> List[Dict]:
    """
    Liest alle Vokabeln mit Kontext aus der Datenbank.
    Kombiniert WORDS, LOOKUPS und BOOK_INFO Tabellen.
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
        vocab_list.append({
            'id': row[0],
            'word': row[1],
            'lang': row[2],
            'usage': row[3] or '',
            'book': row[4] or 'Unknown',
            'authors': row[5] or 'Unknown'
        })
    
    return vocab_list

def separate_by_language(vocab_list: List[Dict]) -> Tuple[List[Dict], List[Dict]]:
    """Trennt Vokabeln nach Sprache (en/de)."""
    en_words = [v for v in vocab_list if v['lang'] and v['lang'].startswith('en')]
    de_words = [v for v in vocab_list if v['lang'] and v['lang'].startswith('de')]
    
    return en_words, de_words

# ============================================================================
# Gemini API Integration
# ============================================================================

def setup_gemini_api():
    """Importiert und konfiguriert die Gemini API."""
    try:
        import google.generativeai as genai
    except ImportError:
        print("❌ Fehler: google-generativeai nicht installiert!")
        print("Installiere mit: pip install google-generativeai")
        sys.exit(1)
    
    if not CONFIG['GEMINI_API_KEY']:
        print("❌ Fehler: GEMINI_API_KEY nicht gesetzt!")
        print("Bitte trage deinen API-Key in der CONFIG ein.")
        sys.exit(1)
    
    genai.configure(api_key=CONFIG['GEMINI_API_KEY'])
    return genai

def create_prompt_for_batch(words: List[Dict], language: str, genai_instance = None) -> str:
    """Erstellt den Prompt für einen Batch von Vokabeln."""
    
    prompt_intro = """Du bist ein Experte für Sprachenlernen und erstellst hochwertige Anki-Karteikarten.

WICHTIGE REGELN:
1. Verben IMMER im Infinitiv angeben
2. Kontextsatz: Die Zielvokabel im Satz mit <b>...</b> fett markieren

"""
    
    if language == 'en':
        prompt_intro += """
AUFGABE: Gib für jede Vokabel NUR zurück:
- EN_definition: LIES DEN KONTEXT! Gib BEIDE Bedeutungen an:
    1. Die Bedeutung die IM KONTEXT verwendet wird (ZUERST!)
    2. Falls es eine andere häufige Bedeutung gibt, auch diese (mit "also:")
    Beispiel: "breeding" im Kontext Person = "upbringing, good manners (also: animal reproduction)"
- DE_gloss: Deutsche Übersetzung die ZUM KONTEXT passt
    REGELN für DE_gloss:
    • Verben im INFINITIV (z.B. "wiegen" NICHT "wiegte")
    • Substantive GROSSGESCHRIEBEN
    • Mehrere Bedeutungen mit Komma trennen (z.B. "rufen, anfunken, kontaktieren")
    • Breite Übersetzung bevorzugen (z.B. "Haufen" NICHT nur "Müllhaufen")
    • Bei Fachbegriffen korrekte deutsche Begriffe (z.B. "Kommandoturm" für "conning tower")
- Notes: Nur wenn WIRKLICH hilfreich! "" wenn nichts zutrifft.
    Erlaubt: 
    • Register (umgangsspr./formell)
    • Variante (BE/AE)
    • Falsche Freunde
    • Formen ZEIGEN (z.B. "go-went-gone" NICHT "irregular")
    • Wendungen
    • Tonalität (z.B. "negative connotation", "formal/literary", "admiring tone")
    • Fremdwort: ERKLÄRE das deutsche Fremdwort! (z.B. "Fremdwort 'heuristisch' = durch Probieren lernend")
      → Bei seltenen Latein/Griechisch-Wörtern (obeisance, supercilious, etc.) IMMER Fremdwort-Note!

⚠️ KONTEXT LESEN! Bedeutung muss zum Satz passen! Tonalität bei wertenden Wörtern!
⚠️ WICHTIG: Original_word, EN_lemma, Context_HTML und Book NICHT ausgeben - werden automatisch ergänzt!

"""
    else:  # de
        prompt_intro += """
AUFGABE: Gib für jede Vokabel NUR zurück:
- DE_definition: LIES DEN KONTEXT! Gib BEIDE Bedeutungen an (einfache Worte):
    1. Die Bedeutung die IM KONTEXT verwendet wird (ZUERST!)
    2. Falls es eine andere häufige Bedeutung gibt, auch diese (mit "auch:")
- Notes: Nur wenn WIRKLICH hilfreich! "" wenn nichts zutrifft.
    Erlaubt: 
    • Register (umgangsspr./formell/gehoben)
    • Variante (regional/Jugend)
    • Falsche Freunde
    • Fremdwort: ERKLÄRE das Fremdwort! (z.B. "Latinismus, bedeutet: ...")
    • Wendungen
    • Tonalität (z.B. "abwertend", "gehoben", "bewundernd")

⚠️ KONTEXT LESEN! Bedeutung muss zum Satz passen! Tonalität bei wertenden Wörtern!
⚠️ WICHTIG: Original_word, DE_lemma, Context_HTML und Book NICHT ausgeben - werden automatisch ergänzt!
"""
    
    # Vokabeln hinzufügen mit Lemmatisierung
    prompt_words = "VOKABELN:\n\n"
    for i, word in enumerate(words, 1):
        # Lemmatisiere das Wort lokal mit spaCy
        lemma = lemmatize_word(word['word'], language)
        
        prompt_words += f"{i}. Wort: {word['word']}\n"
        prompt_words += f"   Lemma: {lemma}\n"
        if word['usage']:
            prompt_words += f"   Kontext: {word['usage']}\n"
        if word['book']:
            # Normalisiere Buchtitel für konsistente Schreibweise (mit Autor aus DB + Gemini)
            normalized_book = normalize_book_title(word['book'], word.get('authors'), genai_instance)
            prompt_words += f"   Buch: {normalized_book}\n"
        
        # Speichere Lemma im word dict für späteren Zugriff
        word['lemma'] = lemma
        
        prompt_words += "\n"
    
    prompt_output = """
AUSGABEFORMAT: Gib ausschließlich ein gültiges JSON-Array zurück, ohne zusätzliche Erklärungen oder Markdown-Formatierung.
Jedes Objekt repräsentiert NUR die generierten Felder für eine Vokabel (in dieser Reihenfolge).

"""
    
    if language == 'en':
        prompt_output += """Beispiel (nur die 3 generierten Felder):
[
  {
    "EN_definition": "upbringing, good manners, and refinement (also: the mating and production of offspring by animals)",
    "DE_gloss": "vornehme Erziehung, gute Manieren",
    "Notes": ""
  },
  {
    "EN_definition": "to collect someone or something (also: to lift, to learn, to improve)",
    "DE_gloss": "abholen, aufsammeln",
    "Notes": "phrasal verb"
  },
  {
    "EN_definition": "to die",
    "DE_gloss": "den Löffel abgeben, sterben",
    "Notes": "idiomatic expression; informal"
  },
  {
    "EN_definition": "the official residence of the British Prime Minister (also: metonym for the UK government)",
    "DE_gloss": "Downing Street",
    "Notes": "proper noun; metonym for UK government"
  },
  {
    "EN_definition": "behaving as though one is superior to others",
    "DE_gloss": "überheblich, hochmütig",
    "Notes": "Fremdwort (lat. 'supercilium' = Augenbraue); formal/literary; negative connotation"
  }
]
"""
    else:
        prompt_output += """Beispiel (nur die 2 generierten Felder):
[
  {
    "DE_definition": "jemanden heftig kritisieren oder anprangern (auch: mit einer Geißel schlagen)",
    "Notes": "gehoben/literarisch"
  },
  {
    "DE_definition": "sterben",
    "Notes": "Redewendung; nicht wörtlich; umgangssprachlich"
  },
  {
    "DE_definition": "jemanden durch ständiges Nerven erschöpfen oder irritieren",
    "Notes": "umgangssprachlich; Partizip II von 'abnerven'"
  },
  {
    "DE_definition": "Amtssitz des US-Präsidenten (auch: Synonym für die US-Regierung)",
    "Notes": "Eigenname; Metonym für US-Regierung"
  }
]
"""
    
    return prompt_intro + prompt_words + prompt_output

def process_batch_with_gemini(genai, words: List[Dict], language: str, batch_num: int = 0) -> Tuple[List[Dict], bool]:
    """
    Verarbeitet einen Batch von Vokabeln mit der Gemini API.
    Gibt zurück: (cards, quota_exceeded)
    quota_exceeded=True bedeutet: Alle weiteren Batches sollten übersprungen werden
    """
    
    if CONFIG['DRY_RUN']:
        print(f"  [DRY RUN] Würde {len(words)} Wörter verarbeiten...")
        return [], False
    
    for attempt in range(CONFIG['MAX_RETRIES']):
        try:
            model = genai.GenerativeModel('gemini-2.0-flash')
            prompt = create_prompt_for_batch(words, language, genai)
            
            # Speichere Raw Input (Prompt) für Debugging
            if CONFIG['SAVE_RAW_INPUTS']:
                output_dir = Path(CONFIG['TSV_OUTPUT_DIR']).parent / 'raw_inputs'  # anki_cards/raw_inputs
                output_dir.mkdir(parents=True, exist_ok=True)
                timestamp = time.strftime('%Y%m%d_%H%M%S')
                input_file = output_dir / f"prompt_{language}_batch{batch_num}_{timestamp}.txt"
                with open(input_file, 'w', encoding='utf-8') as f:
                    f.write(prompt)
            
            if CONFIG['VERBOSE']:
                input_tokens = len(prompt.split())
                print(f" (in: ~{input_tokens})", end="", flush=True)
            
            response = model.generate_content(prompt)
            
            # Token-Statistik anzeigen
            if CONFIG['VERBOSE']:
                output_tokens = len(response.text.split())
                total_tokens = input_tokens + output_tokens
                print(f" (out: ~{output_tokens}) (total: ~{total_tokens})", end="")
            
            # Speichere Raw Response für Debugging
            if CONFIG['SAVE_RAW_RESPONSES']:
                output_dir = Path(CONFIG['TSV_OUTPUT_DIR']).parent / 'raw_responses'  # anki_cards/raw_responses
                output_dir.mkdir(parents=True, exist_ok=True)
                timestamp = time.strftime('%Y%m%d_%H%M%S')
                response_file = output_dir / f"response_{language}_batch{batch_num}_{timestamp}.txt"
                with open(response_file, 'w', encoding='utf-8') as f:
                    f.write(response.text)
            
            # Parse JSON response
            response_text = response.text.strip()
            # Entferne mögliche Markdown-Formatierung
            if response_text.startswith('```json'):
                response_text = response_text[7:]
            if response_text.startswith('```'):
                response_text = response_text[3:]
            if response_text.endswith('```'):
                response_text = response_text[:-3]
            response_text = response_text.strip()
            
            cards = json.loads(response_text)
            
            # Ergänze fehlende Felder aus Input-Daten und ordne neu
            lemma_field = 'EN_lemma' if language == 'en' else 'DE_lemma'
            
            for i, card in enumerate(cards):
                if i >= len(words):
                    # Mehr Karten als Wörter - sollte nicht passieren
                    if CONFIG['VERBOSE']:
                        print(f"\n    ⚠️  Mehr Karten ({len(cards)}) als Wörter ({len(words)}) - breche ab")
                    break
                
                word = words[i]
                lemma = word.get('lemma', word['word'].lower())
                original_word = word['word']
                
                # Erstelle Context_HTML: Kontext mit <b></b> markiertem Wort
                context = word.get('usage', '')
                if context:
                    # Finde das Wort im Kontext (case-insensitive)
                    import re
                    # Escape special regex characters im original_word
                    escaped_word = re.escape(original_word)
                    # Suche nach dem Wort (ganze Wörter, case-insensitive)
                    pattern = re.compile(rf'\b({escaped_word})\b', re.IGNORECASE)
                    context_html = pattern.sub(r'<b>\1</b>', context, count=1)
                else:
                    context_html = ''
                
                # Erstelle neu geordnetes Dictionary: Lemma zuerst, Notes/Book zuletzt
                ordered_card = {lemma_field: lemma}
                ordered_card['Original_word'] = original_word
                
                # Füge die von Gemini generierten Felder hinzu
                if language == 'en':
                    ordered_card['EN_definition'] = card.get('EN_definition', '')
                    ordered_card['DE_gloss'] = card.get('DE_gloss', '')
                else:
                    ordered_card['DE_definition'] = card.get('DE_definition', '')
                
                ordered_card['Context_HTML'] = context_html
                ordered_card['Notes'] = card.get('Notes', '')
                ordered_card['Book'] = ''  # Wird später in add_to_cache gefüllt
                
                # Ersetze die Karte durch die vollständige Version
                card.clear()
                card.update(ordered_card)
            
            # Validiere alle Karten
            valid_cards = []
            invalid_count = 0
            for card in cards:
                # Normalisiere null zu "" für optionale Felder
                if card.get('Notes') is None:
                    card['Notes'] = ""
                if card.get('Book') is None:
                    card['Book'] = ""
                
                is_valid, error_msg = validate_card(card, language)
                if is_valid:
                    valid_cards.append(card)
                else:
                    invalid_count += 1
                    if CONFIG['VERBOSE']:
                        print(f"\n    ⚠️  Ungültige Karte: {error_msg}")
                        log_error(f"Ungültige Karte in Batch {batch_num}: {error_msg}", None)
            
            if invalid_count > 0:
                print(f" ({invalid_count} ungültige Karten übersprungen)", end="")
            
            # Entferne Duplikate
            if CONFIG['SKIP_DUPLICATES']:
                valid_cards = remove_duplicates(valid_cards, language)
            
            return valid_cards, False
            
        except json.JSONDecodeError as e:
            error_msg = f"JSON-Parsing-Fehler in Batch {batch_num}, Versuch {attempt + 1}/{CONFIG['MAX_RETRIES']}"
            print(f"\n  ❌ {error_msg}: {e}")
            log_error(error_msg, e)
            
            if attempt < CONFIG['MAX_RETRIES'] - 1:
                print(f"  ⏳ Warte {CONFIG['RETRY_DELAY']} Sekunden vor erneutem Versuch...")
                time.sleep(CONFIG['RETRY_DELAY'])
            else:
                print(f"  ❌ Batch {batch_num} nach {CONFIG['MAX_RETRIES']} Versuchen übersprungen!")
                return [], False
                
        except Exception as e:
            error_str = str(e)
            
            # Prüfe auf Quota-Fehler (429)
            if '429' in error_str or 'quota' in error_str.lower() or 'limit' in error_str.lower():
                error_msg = f"⚠️  QUOTA-LIMIT ERREICHT in Batch {batch_num}"
                print(f"\n  ❌ {error_msg}")
                print(f"  📊 Gemini Free-Tier Limit überschritten!")
                print(f"  ⏸️  ALLE WEITEREN BATCHES WERDEN ÜBERSPRUNGEN")
                log_error(error_msg, e)
                return [], True  # quota_exceeded = True
            
            error_msg = f"API-Fehler in Batch {batch_num}, Versuch {attempt + 1}/{CONFIG['MAX_RETRIES']}"
            print(f"\n  ❌ {error_msg}: {e}")
            log_error(error_msg, e)
            
            if attempt < CONFIG['MAX_RETRIES'] - 1:
                print(f"  ⏳ Warte {CONFIG['RETRY_DELAY']} Sekunden vor erneutem Versuch...")
                time.sleep(CONFIG['RETRY_DELAY'])
            else:
                print(f"  ❌ Batch {batch_num} nach {CONFIG['MAX_RETRIES']} Versuchen übersprungen!")
                return [], False
    
    return [], False

# ============================================================================
# TSV Export
# ============================================================================

def create_tsv_file(cards: List[Dict], card_type: str, output_dir: Path):
    """Erstellt TSV-Datei für Anki-Import."""
    
    output_dir.mkdir(parents=True, exist_ok=True)
    
    filename = output_dir / f"anki_{card_type}.tsv"
    
    if card_type == 'en_de':
        header = "EN_lemma\tEN_definition\tDE_gloss\tContext_HTML\tBook\tNotes\n"
        lines = [header]
        for card in cards:
            line = f"{card.get('EN_lemma', '')}\t"
            line += f"{card.get('EN_definition', '')}\t"
            line += f"{card.get('DE_gloss', '')}\t"
            line += f"{card.get('Context_HTML', '')}\t"
            line += f"{card.get('Book', '')}\t"
            line += f"{card.get('Notes', '')}\n"
            lines.append(line)
    
    elif card_type == 'de_en':
        header = "DE_gloss\tEN_lemma\tEN_definition\tContext_HTML\tBook\tNotes\n"
        lines = [header]
        for card in cards:
            line = f"{card.get('DE_gloss', '')}\t"
            line += f"{card.get('EN_lemma', '')}\t"
            line += f"{card.get('EN_definition', '')}\t"
            line += f"{card.get('Context_HTML', '')}\t"
            line += f"{card.get('Book', '')}\t"
            line += f"{card.get('Notes', '')}\n"
            lines.append(line)
    
    elif card_type == 'de_de':
        header = "DE_lemma\tDE_definition\tContext_HTML\tBook\tNotes\n"
        lines = [header]
        for card in cards:
            line = f"{card.get('DE_lemma', '')}\t"
            line += f"{card.get('DE_definition', '')}\t"
            line += f"{card.get('Context_HTML', '')}\t"
            line += f"{card.get('Book', '')}\t"
            line += f"{card.get('Notes', '')}\n"
            lines.append(line)
    
    with open(filename, 'w', encoding='utf-8') as f:
        f.writelines(lines)
    
    print(f"✅ TSV-Datei erstellt: {filename} ({len(cards)} Karten)")

# ============================================================================
# Main Processing
# ============================================================================

def main():
    print("=" * 70)
    print("Kindle to Anki Converter")
    print("=" * 70)
    print()
    
    # 1. Konfiguration prüfen
    print("📋 Konfiguration:")
    print(f"  - Datenbank: {CONFIG['VOCAB_DB_PATH']}")
    print(f"  - TSV-Ausgabe: {CONFIG['TSV_OUTPUT_DIR']}")
    print(f"  - APKG-Ausgabe: {CONFIG['APKG_OUTPUT_DIR']}")
    print(f"  - Batch-Größe: {CONFIG['BATCH_SIZE']}")
    print(f"  - Pause zwischen Batches: {CONFIG['DELAY_BETWEEN_BATCHES']}s")
    print(f"  - Max. Wiederholungen: {CONFIG['MAX_RETRIES']}")
    print(f"  - API-Key gesetzt: {'✅' if CONFIG['GEMINI_API_KEY'] else '❌'}")
    print(f"  - Duplikate überspringen: {'✅' if CONFIG['SKIP_DUPLICATES'] else '❌'}")
    print(f"  - Bereits übersetzte überspringen: {'✅' if CONFIG['SKIP_TRANSLATED'] else '❌'}")
    print(f"  - APKG-Pakete erstellen: {'✅' if CONFIG['CREATE_APKG'] else '❌'}")
    print()
    
    # 2. Datenbank laden
    print("📚 Lade Vokabeln aus Datenbank...")
    conn = connect_to_db(CONFIG['VOCAB_DB_PATH'])
    vocab_data = get_vocabulary_data(conn)
    en_words, de_words = separate_by_language(vocab_data)
    conn.close()
    
    print(f"  - Gesamt: {len(vocab_data)} Vokabeln")
    print(f"  - Englisch: {len(en_words)} Vokabeln")
    print(f"  - Deutsch: {len(de_words)} Vokabeln")
    print()
    
    # 3. Cache für bereits übersetzte Vokabeln laden
    translated_cache = load_translated_cache()
    cached_en = len(translated_cache.get('en_words', {}))
    cached_de = len(translated_cache.get('de_words', {}))
    
    print("📦 Cache:")
    print(f"  - Bereits übersetzte englische Vokabeln: {cached_en}")
    print(f"  - Bereits übersetzte deutsche Vokabeln: {cached_de}")
    
    # Lade Buchtitel in RAM für konsistente Schreibweise
    load_book_titles_from_cache(translated_cache)
    
    # Filtere bereits übersetzte Vokabeln heraus
    if CONFIG['SKIP_TRANSLATED']:
        en_words_original_count = len(en_words)
        de_words_original_count = len(de_words)
        
        en_words = [w for w in en_words if not is_word_translated(w['id'], 'en', translated_cache)]
        de_words = [w for w in de_words if not is_word_translated(w['id'], 'de', translated_cache)]
        
        en_skipped = en_words_original_count - len(en_words)
        de_skipped = de_words_original_count - len(de_words)
        
        print(f"  - Überspringe {en_skipped} bereits übersetzte englische Vokabeln")
        print(f"  - Überspringe {de_skipped} bereits übersetzte deutsche Vokabeln")
        print(f"  - Neue englische Vokabeln zu übersetzen: {len(en_words)}")
        print(f"  - Neue deutsche Vokabeln zu übersetzen: {len(de_words)}")
    print()
    
    # 4. Fortschritt laden
    progress = load_progress()
    
    # 5. Gemini API initialisieren
    if not CONFIG['DRY_RUN']:
        print("🤖 Initialisiere Gemini API...")
        genai = setup_gemini_api()
        print("  ✅ API bereit")
        print()
    else:
        genai = None
        print("⚠️  DRY RUN Modus - keine API-Calls")
        print()
    
    # 6. Englische Vokabeln verarbeiten
    en_cards_new = []
    if CONFIG['CREATE_EN_DE_CARDS'] and en_words:
        print(f"🇬🇧 Verarbeite {len(en_words)} neue englische Vokabeln...")
        
        batches = [en_words[i:i + CONFIG['BATCH_SIZE']] 
                   for i in range(0, len(en_words), CONFIG['BATCH_SIZE'])]
        
        quota_exceeded = False
        
        for i, batch in enumerate(batches, 1):
            if quota_exceeded:
                print(f"  ⏸️  Batch {i}/{len(batches)} übersprungen (Quota-Limit)")
                continue
                
            print(f"  Batch {i}/{len(batches)} ({len(batch)} Wörter)...", end=" ")
            cards, quota_exceeded = process_batch_with_gemini(genai, batch, 'en', i)
            
            if cards:
                en_cards_new.extend(cards)
                # Füge zum Cache hinzu
                add_to_cache(cards, batch, 'en', translated_cache)
                save_translated_cache(translated_cache)
                
                # Notes-Statistik anzeigen
                notes_count = sum(1 for c in cards if c.get('Notes') and c['Notes'].strip())
                notes_percent = (notes_count / len(cards) * 100) if cards else 0
                print(f"✅ ({notes_count}/{len(cards)} mit Notes = {notes_percent:.0f}%)")
            elif quota_exceeded:
                print(f"\n  ⚠️  QUOTA-LIMIT: Restliche {len(batches) - i} Batches werden übersprungen!")
                break
            
            if i < len(batches) and not quota_exceeded:
                time.sleep(CONFIG['DELAY_BETWEEN_BATCHES'])
        
        print()
    
    # 7. Deutsche Vokabeln verarbeiten
    de_cards_new = []
    if CONFIG['CREATE_DE_DE_CARDS'] and de_words:
        print(f"🇩🇪 Verarbeite {len(de_words)} neue deutsche Vokabeln...")
        
        batches = [de_words[i:i + CONFIG['BATCH_SIZE']] 
                   for i in range(0, len(de_words), CONFIG['BATCH_SIZE'])]
        
        quota_exceeded = False
        
        for i, batch in enumerate(batches, 1):
            if quota_exceeded:
                print(f"  ⏸️  Batch {i}/{len(batches)} übersprungen (Quota-Limit)")
                continue
                
            print(f"  Batch {i}/{len(batches)} ({len(batch)} Wörter)...", end=" ")
            cards, quota_exceeded = process_batch_with_gemini(genai, batch, 'de', i)
            
            if cards:
                de_cards_new.extend(cards)
                # Füge zum Cache hinzu
                add_to_cache(cards, batch, 'de', translated_cache)
                save_translated_cache(translated_cache)
                
                # Notes-Statistik anzeigen
                notes_count = sum(1 for c in cards if c.get('Notes') and c['Notes'].strip())
                notes_percent = (notes_count / len(cards) * 100) if cards else 0
                print(f"✅ ({notes_count}/{len(cards)} mit Notes = {notes_percent:.0f}%)")
            elif quota_exceeded:
                print(f"\n  ⚠️  QUOTA-LIMIT: Restliche {len(batches) - i} Batches werden übersprungen!")
                break
            
            if i < len(batches) and not quota_exceeded:
                time.sleep(CONFIG['DELAY_BETWEEN_BATCHES'])
        
        print()
    
    # 8. Kombiniere neue Karten mit gecachten Karten
    all_en_cards = list(translated_cache.get('en_words', {}).values())
    all_de_cards = list(translated_cache.get('de_words', {}).values())
    
    # 9. TSV-Dateien erstellen
    tsv_output_dir = Path(CONFIG['TSV_OUTPUT_DIR'])
    
    if all_en_cards and CONFIG['CREATE_EN_DE_CARDS']:
        create_tsv_file(all_en_cards, 'en_de', tsv_output_dir)
        if CONFIG['CREATE_DE_EN_CARDS']:
            create_tsv_file(all_en_cards, 'de_en', tsv_output_dir)
    
    if all_de_cards and CONFIG['CREATE_DE_DE_CARDS']:
        create_tsv_file(all_de_cards, 'de_de', tsv_output_dir)
    
    # 10. APKG-Pakete erstellen (optional)
    if CONFIG['CREATE_APKG']:
        print()
        print("=" * 70)
        print("📦 Erstelle APKG-Pakete...")
        print("=" * 70)
        try:
            from tsv_to_apkg import convert_all_tsv_to_apkg
            
            apkg_output_dir = Path(CONFIG['APKG_OUTPUT_DIR'])
            results = convert_all_tsv_to_apkg(tsv_output_dir, apkg_output_dir)
            
            successful = sum(1 for success in results.values() if success)
            print()
            print(f"✅ {successful}/{len(results)} APKG-Pakete erfolgreich erstellt!")
            
        except ImportError:
            print()
            print("⚠️  Modul 'genanki' nicht gefunden!")
            print("   Installiere mit: pip install genanki")
            print("   APKG-Erstellung übersprungen. TSV-Dateien sind verfügbar.")
        except Exception as e:
            print()
            print(f"❌ Fehler bei APKG-Erstellung: {e}")
            print("   TSV-Dateien sind verfügbar und können manuell importiert werden.")
    
    print()
    print("=" * 70)
    print("✅ Fertig!")
    print("=" * 70)
    print()
    print("📊 Statistik:")
    print(f"  - Neue englische Karten: {len(en_cards_new)}")
    print(f"  - Neue deutsche Karten: {len(de_cards_new)}")
    print(f"  - Gesamt englische Karten (inkl. Cache): {len(all_en_cards)}")
    print(f"  - Gesamt deutsche Karten (inkl. Cache): {len(all_de_cards)}")
    print()
    
    if CONFIG['CREATE_APKG']:
        print("📁 APKG-Pakete (für direkten Import):")
        print(f"   {Path(CONFIG['APKG_OUTPUT_DIR']).absolute()}")
        print()
    
    print("📁 TSV-Dateien (für manuellen Import):")
    print(f"   {Path(CONFIG['TSV_OUTPUT_DIR']).absolute()}")
    print()
    print("💡 Tipp: Beim nächsten Lauf werden bereits übersetzte Vokabeln")
    print("   automatisch übersprungen. Nur neue Vokabeln werden übersetzt!")
    print()

if __name__ == "__main__":
    main()