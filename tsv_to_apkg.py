#!/usr/bin/env python3
"""
TSV to APKG Converter
Converts Anki TSV files to APKG packages with custom card templates
"""

import genanki
import csv
from pathlib import Path
from typing import List, Dict, Tuple
import random
import hashlib

# ============================================================================
# Card Templates & Styling
# ============================================================================

# Shared CSS for all card types (from ANKI_TEMPLATES.md)
BASE_CSS = """
/* === Basis === */
.card {
  padding: clamp(1.5rem, 4vw, 3rem) clamp(1rem, 3vw, 2rem);
  background-color: #ffffff;
  color: #1a1a1a;
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
  font-size: 16px;
  text-align: center;
  max-width: 900px;
  margin: 0 auto;
  line-height: 1.6;
}

/* === Quelle (Buch) === */
.source {
  margin-bottom: 0.75rem;
  color: #666;
  font-size: clamp(0.75rem, 1.5vw, 0.875rem);
  font-style: italic;
  opacity: 0.8;
}

/* === Type Label === */
.type {
  margin-bottom: 0.5rem;
  color: #555;
  font-size: clamp(0.7rem, 1.5vw, 0.8rem);
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.1em;
}

/* === Frage (Vorderseite) === */
.question {
  margin: 1.5rem 0;
  font-size: clamp(2.5rem, 6vw, 4rem);
  font-weight: 700;
  color: #000;
  letter-spacing: -0.02em;
}

.question--small {
  margin: 0.5rem 0 1rem 0;
  font-size: clamp(1.5rem, 3.5vw, 2rem);
  opacity: 0.7;
}

/* === Hint (Definition auf Vorderseite) === */
.hint {
  max-width: 35em;
  margin: 1.5rem auto;
  padding: 1rem 1.5rem;
  background-color: #f5f5f5;
  border-left: 3px solid #999;
  color: #555;
  font-size: clamp(0.9rem, 2vw, 1.05rem);
  font-style: italic;
  text-align: left;
  line-height: 1.5;
}

/* === Trennlinie === */
hr {
  margin: 2rem 0;
  border: none;
  border-top: 2px solid #e0e0e0;
}

/* === Definition (Rückseite) === */
.definition {
  max-width: 35em;
  margin: 1.5rem auto;
  padding: 0.75rem 1rem;
  background-color: #fef3c7;
  border-left: 3px solid #f59e0b;
  color: #78350f;
  font-size: clamp(0.9rem, 2vw, 1.05rem);
  font-style: italic;
  text-align: left;
  line-height: 1.5;
}

/* === Kontext === */
.context {
  max-width: 40em;
  margin: 2rem auto 1rem auto;
  padding: 1.25rem;
  background-color: #f9fafb;
  border: 1px solid #e5e7eb;
  border-radius: 6px;
  text-align: left;
}

.context-label {
  margin-bottom: 0.5rem;
  color: #6b7280;
  font-size: clamp(0.75rem, 1.5vw, 0.85rem);
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.05em;
}

.context {
  color: #374151;
  font-size: clamp(0.9rem, 2vw, 1.05rem);
  line-height: 1.7;
}

.context b {
  color: #1e40af;
  font-weight: 700;
  background-color: #dbeafe;
  padding: 0.1em 0.3em;
  border-radius: 3px;
}

/* === Notes === */
.notes {
  max-width: 35em;
  margin: 1.5rem auto;
  padding: 1rem 1.25rem;
  background-color: #fef9e7;
  border-left: 3px solid #f59e0b;
  color: #92400e;
  font-size: clamp(0.85rem, 1.8vw, 0.95rem);
  text-align: left;
  line-height: 1.5;
}

/* === Mobile Optimierung === */
@media (max-width: 600px) {
  .card {
    padding: 1.5rem 1rem;
  }
  
  .context,
  .hint,
  .definition,
  .notes {
    padding: 0.75rem 1rem;
  }
}
"""

# Night mode CSS (shared)
NIGHT_MODE_CSS = """
/* === Night Mode === */
.night_mode .card,
.nightMode .card {
  background-color: #1e1e1e;
  color: #e0e0e0;
}

.night_mode .type,
.nightMode .type {
  color: #999;
}

.night_mode .question,
.nightMode .question {
  color: #ffffff;
}

.night_mode .hint,
.nightMode .hint {
  background-color: #2a2a2a;
  border-left-color: #666;
  color: #b0b0b0;
}

.night_mode hr,
.nightMode hr {
  border-top-color: #404040;
}

.night_mode .definition,
.nightMode .definition {
  background-color: #3a2e1e;
  border-left-color: #fbbf24;
  color: #fcd34d;
}

.night_mode .context,
.nightMode .context {
  background-color: #2a2a2a;
  border-color: #404040;
  color: #b0b0b0;
}

.night_mode .context b,
.nightMode .context b {
  color: #93c5fd;
  background-color: #1e3a5f;
}

.night_mode .notes,
.nightMode .notes {
  background-color: #3a2e1e;
  border-left-color: #fbbf24;
  color: #fcd34d;
}

.night_mode .source,
.nightMode .source {
  color: #999;
}
"""

# EN→DE specific CSS (Blue)
EN_DE_ANSWER_CSS = """
/* === Antwort (Rückseite) - BLAU === */
.answer {
  margin: 1.5rem 0;
  padding: 1rem 1.5rem;
  background-color: #f0f9ff;
  border-left: 4px solid #3b82f6;
  font-size: clamp(1.75rem, 4vw, 2.75rem);
  font-weight: 600;
  color: #1e40af;
}

.night_mode .answer,
.nightMode .answer {
  background-color: #1e3a5f;
  border-left-color: #60a5fa;
  color: #93c5fd;
}
"""

# DE→EN specific CSS (Red)
DE_EN_ANSWER_CSS = """
/* === Antwort (Rückseite) - ROT === */
.answer {
  margin: 1.5rem 0;
  padding: 1rem 1.5rem;
  background-color: #fef2f2;
  border-left: 4px solid #ef4444;
  font-size: clamp(1.75rem, 4vw, 2.75rem);
  font-weight: 600;
  color: #991b1b;
}

.night_mode .answer,
.nightMode .answer {
  background-color: #3a1e1e;
  border-left-color: #f87171;
  color: #fca5a5;
}
"""

# DE→DE specific CSS (Teal)
DE_DE_ANSWER_CSS = """
/* === Antwort (Rückseite) - TÜRKIS === */
.answer {
  margin: 1.5rem 0;
  padding: 1rem 1.5rem;
  background-color: #f0fdfa;
  border-left: 4px solid #14b8a6;
  font-size: clamp(1.75rem, 4vw, 2.75rem);
  font-weight: 600;
  color: #115e59;
}

.night_mode .answer,
.nightMode .answer {
  background-color: #1e3a38;
  border-left-color: #5eead4;
  color: #99f6e4;
}
"""

# ============================================================================
# Model Definitions (Anki Note Types)
# ============================================================================

def create_en_de_model() -> genanki.Model:
    """Creates the EN→DE card model (English → Deutsch)"""
    
    # Fixed model ID for EN→DE (ensures consistent GUIDs across runs)
    model_id = 1607392319  # Hash of "Kindle_EN_DE"
    
    return genanki.Model(
        model_id,
        'Kindle EN→DE',
        fields=[
            {'name': 'EN_lemma'},
            {'name': 'EN_definition'},
            {'name': 'DE_gloss'},
            {'name': 'Context_HTML'},
            {'name': 'Book'},
            {'name': 'Notes'},
        ],
        templates=[
            {
                'name': 'English → Deutsch',
                'qfmt': '''<div class="card">
  {{#Book}}
  <div class="source">📚 {{Book}}</div>
  {{/Book}}
  
  <div class="type">English → Deutsch</div>
  <div class="question">{{EN_lemma}}</div>
  
  {{#Context_HTML}}
  <div class="context">
    <div class="context-label">Kontext:</div>
    {{Context_HTML}}
  </div>
  {{/Context_HTML}}
</div>''',
                'afmt': '''<div class="card">
  {{#Book}}
  <div class="source">📚 {{Book}}</div>
  {{/Book}}
  
  <div class="type">English → Deutsch</div>
  <div class="question question--small">{{EN_lemma}}</div>
  
  <hr id="answer">
  
  <div class="answer">{{DE_gloss}}</div>
  
  {{#EN_definition}}
  <div class="definition">{{EN_definition}}</div>
  {{/EN_definition}}
  
  {{#Context_HTML}}
  <div class="context">
    <div class="context-label">Kontext:</div>
    {{Context_HTML}}
  </div>
  {{/Context_HTML}}
  
  {{#Notes}}
  <div class="notes">💡 {{Notes}}</div>
  {{/Notes}}
</div>''',
            }
        ],
        css=BASE_CSS + EN_DE_ANSWER_CSS + NIGHT_MODE_CSS
    )


def create_de_en_model() -> genanki.Model:
    """Creates the DE→EN card model (Deutsch → English)"""
    
    # Fixed model ID for DE→EN (ensures consistent GUIDs across runs)
    model_id = 1607392320  # Hash of "Kindle_DE_EN"
    
    return genanki.Model(
        model_id,
        'Kindle DE→EN',
        fields=[
            {'name': 'DE_gloss'},
            {'name': 'EN_lemma'},
            {'name': 'EN_definition'},
            {'name': 'Context_HTML'},
            {'name': 'Book'},
            {'name': 'Notes'},
        ],
        templates=[
            {
                'name': 'Deutsch → English',
                'qfmt': '''<div class="card">
  {{#Book}}
  <div class="source">📚 {{Book}}</div>
  {{/Book}}
  
  <div class="type">Deutsch → English</div>
  <div class="question">{{DE_gloss}}</div>
  
  {{#Context_HTML}}
  <div class="context">
    <div class="context-label">Kontext:</div>
    {{Context_HTML}}
  </div>
  {{/Context_HTML}}
</div>''',
                'afmt': '''<div class="card">
  {{#Book}}
  <div class="source">📚 {{Book}}</div>
  {{/Book}}
  
  <div class="type">Deutsch → English</div>
  <div class="question question--small">{{DE_gloss}}</div>
  
  <hr id="answer">
  
  <div class="answer">{{EN_lemma}}</div>
  
  {{#EN_definition}}
  <div class="definition">{{EN_definition}}</div>
  {{/EN_definition}}
  
  {{#Context_HTML}}
  <div class="context">
    <div class="context-label">Kontext:</div>
    {{Context_HTML}}
  </div>
  {{/Context_HTML}}
  
  {{#Notes}}
  <div class="notes">💡 {{Notes}}</div>
  {{/Notes}}
</div>''',
            }
        ],
        css=BASE_CSS + DE_EN_ANSWER_CSS + NIGHT_MODE_CSS
    )


def create_de_de_model() -> genanki.Model:
    """Creates the DE→DE card model (Deutsche Vokabel)"""
    
    # Fixed model ID for DE→DE (ensures consistent GUIDs across runs)
    model_id = 1607392321  # Hash of "Kindle_DE_DE"
    
    return genanki.Model(
        model_id,
        'Kindle DE→DE',
        fields=[
            {'name': 'DE_lemma'},
            {'name': 'DE_definition'},
            {'name': 'Context_HTML'},
            {'name': 'Book'},
            {'name': 'Notes'},
        ],
        templates=[
            {
                'name': 'Deutsche Vokabel',
                'qfmt': '''<div class="card">
  {{#Book}}
  <div class="source">📚 {{Book}}</div>
  {{/Book}}
  
  <div class="type">Deutsche Vokabel</div>
  <div class="question">{{DE_lemma}}</div>
  
  {{#Context_HTML}}
  <div class="context">
    <div class="context-label">Kontext:</div>
    {{Context_HTML}}
  </div>
  {{/Context_HTML}}
</div>''',
                'afmt': '''<div class="card">
  {{#Book}}
  <div class="source">📚 {{Book}}</div>
  {{/Book}}
  
  <div class="type">Deutsche Vokabel</div>
  <div class="question question--small">{{DE_lemma}}</div>
  
  <hr id="answer">
  
  <div class="answer">{{DE_definition}}</div>
  
  {{#Context_HTML}}
  <div class="context">
    <div class="context-label">Kontext:</div>
    {{Context_HTML}}
  </div>
  {{/Context_HTML}}
  
  {{#Notes}}
  <div class="notes">💡 {{Notes}}</div>
  {{/Notes}}
</div>''',
            }
        ],
        css=BASE_CSS + DE_DE_ANSWER_CSS + NIGHT_MODE_CSS
    )


# ============================================================================
# TSV to APKG Conversion
# ============================================================================

def generate_guid_from_lemma(lemma: str, model_id: int) -> int:
    """
    Generiert eine eindeutige GUID basierend nur auf dem Lemma-Feld.
    
    Dadurch werden Notizen mit gleichem Lemma als identisch erkannt,
    auch wenn sich andere Felder (Definition, Notes) ändern.
    
    Beim Re-Import werden alte Karten mit gleichem Lemma überschrieben,
    aber der Learning-Fortschritt bleibt erhalten!
    
    Args:
        lemma: Das Lemma (erstes Feld der Karte)
        model_id: Die Model-ID
    
    Returns:
        GUID als Integer
    """
    # Normalisiere Lemma (lowercase, whitespace trimmen)
    normalized_lemma = lemma.strip().lower()
    
    # Erstelle eindeutigen Hash aus Lemma + Model ID
    hash_str = f"{model_id}_{normalized_lemma}"
    hash_bytes = hashlib.md5(hash_str.encode('utf-8')).digest()
    
    # Konvertiere zu Integer (Anki braucht Integers für GUIDs)
    guid = int.from_bytes(hash_bytes[:8], byteorder='big', signed=True)
    
    return guid


def read_tsv_file(tsv_path: Path, card_type: str) -> List[List[str]]:
    """
    Reads a TSV file and returns rows mapped to the correct APKG field order
    
    TSV structure:
    - EN→DE (anki_en_de.tsv): EN_lemma | Original_word | EN_definition | DE_gloss | Context_HTML | Book | Notes
    - DE→EN (anki_de_en.tsv): DE_gloss | EN_lemma | Original_word | EN_definition | Context_HTML | Book | Notes
    - DE→DE (anki_de_de.tsv): DE_lemma | Original_word | DE_definition | Context_HTML | Book | Notes
    
    For EN words (anki_en_de.tsv):
        - EN_lemma = English lemma (e.g., "go")
        - Original_word = English word form (e.g., "going")
        - EN_definition = English definition
        - DE_gloss = German translation (e.g., "gehen")
        - Context_HTML = Context sentence with <b>word</b>
    
    For DE words (anki_de_de.tsv):
        - DE_lemma = German lemma (e.g., "geißeln")
        - Original_word = German word form (e.g., "geißelten")
        - DE_definition = German definition
        - Context_HTML = Context sentence with <b>word</b>
    
    Args:
        tsv_path: Path to TSV file
        card_type: 'en_de', 'de_en', or 'de_de'
    
    Returns:
        List of rows, each row is a list of field values in APKG field order
    """
    rows = []
    with open(tsv_path, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f, delimiter='\t')
        
        for row_dict in reader:
            # Map TSV columns to APKG fields based on card type
            if card_type == 'en_de':
                # EN→DE cards: English word with German translation
                # APKG fields: EN_lemma, EN_definition, DE_gloss, Context_HTML, Book, Notes
                row = [
                    row_dict.get('EN_lemma', ''),        # EN_lemma
                    row_dict.get('EN_definition', ''),   # EN_definition
                    row_dict.get('DE_gloss', ''),        # DE_gloss
                    row_dict.get('Context_HTML', ''),    # Context_HTML
                    row_dict.get('Book', ''),            # Book
                    row_dict.get('Notes', '')            # Notes
                ]
            elif card_type == 'de_en':
                # DE→EN cards: REVERSE of EN→DE (German translation → English word)
                # APKG fields: DE_gloss, EN_lemma, EN_definition, Context_HTML, Book, Notes
                row = [
                    row_dict.get('DE_gloss', ''),        # DE_gloss (German translation = front)
                    row_dict.get('EN_lemma', ''),        # EN_lemma (English word = back)
                    row_dict.get('EN_definition', ''),   # EN_definition
                    row_dict.get('Context_HTML', ''),    # Context_HTML
                    row_dict.get('Book', ''),            # Book
                    row_dict.get('Notes', '')            # Notes
                ]
            elif card_type == 'de_de':
                # DE→DE cards: German word with German definition
                # APKG fields: DE_lemma, DE_definition, Context_HTML, Book, Notes
                row = [
                    row_dict.get('DE_lemma', ''),        # DE_lemma
                    row_dict.get('DE_definition', ''),   # DE_definition
                    row_dict.get('Context_HTML', ''),    # Context_HTML
                    row_dict.get('Book', ''),            # Book
                    row_dict.get('Notes', '')            # Notes
                ]
            else:
                # Invalid card_type
                continue
            
            rows.append(row)
    
    return rows


def convert_tsv_to_apkg(tsv_path: Path, output_path: Path, card_type: str) -> bool:
    """
    Converts a TSV file to an APKG package
    
    Args:
        tsv_path: Path to input TSV file
        output_path: Path to output APKG file
        card_type: 'en_de', 'de_en', or 'de_de'
    
    Returns:
        True if successful, False otherwise
    """
    
    if not tsv_path.exists():
        print(f"❌ TSV-Datei nicht gefunden: {tsv_path}")
        return False
    
    # Determine model and deck name based on card type
    if card_type == 'en_de':
        model = create_en_de_model()
        deck_name = 'Kindle::EN→DE'
    elif card_type == 'de_en':
        model = create_de_en_model()
        deck_name = 'Kindle::DE→EN'
    elif card_type == 'de_de':
        model = create_de_de_model()
        deck_name = 'Kindle::DE→DE'
    else:
        print(f"❌ Unbekannter Kartentyp: {card_type}")
        return False
    
    # Read TSV with correct field mapping
    rows = read_tsv_file(tsv_path, card_type)
    
    if len(rows) == 0:
        print(f"⚠️  TSV-Datei ist leer: {tsv_path}")
        return False
    
    # Create deck
    deck_id = random.randrange(1 << 30, 1 << 31)
    deck = genanki.Deck(deck_id, deck_name)
    
    # Add notes to deck with custom GUID based on lemma only
    for row in rows:
        # Ensure all fields are strings and handle empty fields
        fields = [str(field) if field else '' for field in row]
        
        # Extract lemma (first field) for GUID generation
        lemma = fields[0]
        
        # Generate GUID from lemma only (ensures same lemma = same GUID)
        guid = generate_guid_from_lemma(lemma, model.model_id)
        
        note = genanki.Note(
            model=model,
            fields=fields,
            guid=guid  # Custom GUID: Updates existing cards on re-import
        )
        deck.add_note(note)
    
    # Create package and write to file
    package = genanki.Package(deck)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    package.write_to_file(str(output_path))
    
    print(f"✅ APKG erstellt: {output_path} ({len(rows)} Karten)")
    return True


def convert_all_tsv_to_apkg(tsv_dir: Path, apkg_dir: Path) -> Dict[str, bool]:
    """
    Converts all TSV files in a directory to APKG packages
    
    Strategy:
    - anki_en_de.tsv: Create TWO decks (EN→DE and reverse DE→EN) from same data
    - anki_de_de.tsv: Create one deck (DE→DE) for German vocabulary
    - anki_de_en.tsv: SKIP (not needed, handled by reverse of anki_en_de.tsv)
    
    Args:
        tsv_dir: Directory containing TSV files
        apkg_dir: Directory where APKG files will be saved
    
    Returns:
        Dictionary with conversion results {filename: success}
    """
    
    results = {}
    
    # 1. Convert anki_en_de.tsv → EN→DE deck
    tsv_path = tsv_dir / 'anki_en_de.tsv'
    if tsv_path.exists():
        apkg_path = apkg_dir / 'anki_en_de.apkg'
        success = convert_tsv_to_apkg(tsv_path, apkg_path, 'en_de')
        results['anki_en_de.tsv → anki_en_de.apkg'] = success
    else:
        print(f"⏭️  Übersprungen (nicht gefunden): anki_en_de.tsv")
        results['anki_en_de.tsv'] = False
    
    # 2. Convert anki_en_de.tsv → DE→EN deck (REVERSE!)
    if tsv_path.exists():
        apkg_path = apkg_dir / 'anki_de_en.apkg'
        success = convert_tsv_to_apkg(tsv_path, apkg_path, 'de_en')
        results['anki_en_de.tsv → anki_de_en.apkg (reverse)'] = success
    else:
        results['anki_de_en.apkg'] = False
    
    # 3. Convert anki_de_de.tsv → DE→DE deck
    tsv_path = tsv_dir / 'anki_de_de.tsv'
    if tsv_path.exists():
        apkg_path = apkg_dir / 'anki_de_de.apkg'
        success = convert_tsv_to_apkg(tsv_path, apkg_path, 'de_de')
        results['anki_de_de.tsv → anki_de_de.apkg'] = success
    else:
        print(f"⏭️  Übersprungen (nicht gefunden): anki_de_de.tsv")
        results['anki_de_de.tsv'] = False
    
    return results


# ============================================================================
# Main Entry Point
# ============================================================================

def main():
    """Main function for standalone execution"""
    print("=" * 70)
    print("TSV to APKG Converter")
    print("=" * 70)
    print()
    
    # Default paths
    tsv_dir = Path('anki_cards/tsv_files')
    apkg_dir = Path('anki_cards/apkg_files')
    
    print(f"📂 TSV-Verzeichnis: {tsv_dir}")
    print(f"📦 APKG-Verzeichnis: {apkg_dir}")
    print()
    
    # Convert all TSV files
    results = convert_all_tsv_to_apkg(tsv_dir, apkg_dir)
    
    # Summary
    print()
    print("=" * 70)
    print("Zusammenfassung:")
    successful = sum(1 for success in results.values() if success)
    print(f"  - Erfolgreich konvertiert: {successful}/{len(results)}")
    
    if successful > 0:
        print()
        print("🎉 APKG-Dateien können jetzt in Anki importiert werden!")
        print("   Die Karten enthalten die Ultimate UX V2 Templates mit:")
        print("   ✅ Progressive Disclosure")
        print("   ✅ Night Mode Support")
        print("   ✅ Farbcodierte Antworten (Blau/Rot/Türkis)")
        print("   ✅ Responsive Design für Mobile")
    
    print("=" * 70)


if __name__ == "__main__":
    main()
