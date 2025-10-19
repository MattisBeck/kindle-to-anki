#!/usr/bin/env python3
"""
TSV to APKG Converter
Converts Anki TSV files to APKG packages with custom card templates
"""

import genanki
import csv
from pathlib import Path
from typing import Dict, List, Optional
import random
import hashlib

from kindle_to_anki.config import (
  build_field_key,
  format_language_pair,
  get_language_meta,
  validate_language_configuration,
)

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


def generate_model_id(deck_type: str, native_language: str, target_language: str) -> int:
    """Create a stable, deck-specific model ID."""
    base = f"Kindle::{deck_type}:{native_language}:{target_language}"
    digest = hashlib.md5(base.encode('utf-8')).digest()
    return int.from_bytes(digest[:4], byteorder='big') & 0x7FFFFFFF


def create_model(deck_type: str, native_language: str, target_language: str) -> genanki.Model:
    """Create a genanki.Model instance for the requested deck type."""

    native_meta = get_language_meta(native_language)
    target_meta = get_language_meta(target_language)

    model_id = generate_model_id(deck_type, native_language, target_language)

    native_lemma_key = build_field_key(native_language, 'lemma')
    native_definition_key = build_field_key(native_language, 'definition')
    native_gloss_key = build_field_key(native_language, 'gloss')
    target_lemma_key = build_field_key(target_language, 'lemma')
    target_definition_key = build_field_key(target_language, 'definition')

    if deck_type == 'foreign_native':
        model_name = f"Kindle {target_language.upper()}→{native_language.upper()}"
        type_label = f"{target_meta['gemini_label']} → {native_meta['gemini_label']}"
        fields = [
            {'name': target_lemma_key},
            {'name': target_definition_key},
            {'name': native_gloss_key},
            {'name': 'Context_HTML'},
            {'name': 'Book'},
            {'name': 'Notes'},
        ]

        qfmt = """<div class="card">
  {{{{#Book}}}}
  <div class="source">📚 {{{{Book}}}}</div>
  {{{{/Book}}}}
  
  <div class="type">{type_label}</div>
  <div class="question">{{{{{target_lemma}}}}}</div>
  
  {{{{#Context_HTML}}}}
  <div class="context">
    <div class="context-label">Kontext:</div>
    {{{{Context_HTML}}}}
  </div>
  {{{{/Context_HTML}}}}
</div>""".format(type_label=type_label, target_lemma=target_lemma_key)

        afmt = """<div class="card">
  {{{{#Book}}}}
  <div class="source">📚 {{{{Book}}}}</div>
  {{{{/Book}}}}
  
  <div class="type">{type_label}</div>
  <div class="question question--small">{{{{{target_lemma}}}}}</div>
  
  <hr id="answer">
  
  <div class="answer">{{{{{native_gloss}}}}}</div>
  
  {{{{#{target_definition}}}}}
  <div class="definition">{{{{{target_definition}}}}}</div>
  {{{{/{target_definition}}}}}
  
  {{{{#Context_HTML}}}}
  <div class="context">
    <div class="context-label">Kontext:</div>
    {{{{Context_HTML}}}}
  </div>
  {{{{/Context_HTML}}}}
  
  {{{{#Notes}}}}
  <div class="notes">💡 {{{{Notes}}}}</div>
  {{{{/Notes}}}}
</div>""".format(
            type_label=type_label,
            target_lemma=target_lemma_key,
            native_gloss=native_gloss_key,
            target_definition=target_definition_key,
        )

        css = BASE_CSS + EN_DE_ANSWER_CSS + NIGHT_MODE_CSS
        model_kwargs = {}

    elif deck_type == 'native_foreign':
        model_name = f"Kindle {native_language.upper()}→{target_language.upper()}"
        type_label = f"{native_meta['gemini_label']} → {target_meta['gemini_label']}"
        fields = [
            {'name': native_gloss_key},
            {'name': target_lemma_key},
            {'name': target_definition_key},
            {'name': 'Context_HTML'},
            {'name': 'Book'},
            {'name': 'Notes'},
        ]

        qfmt = """<div class="card">
  {{{{#Book}}}}
  <div class="source">📚 {{{{Book}}}}</div>
  {{{{/Book}}}}
  
  <div class="type">{type_label}</div>
  <div class="question">{{{{{native_gloss}}}}}</div>
  
  {{{{#Context_HTML}}}}
  <div class="context">
    <div class="context-label">Kontext:</div>
    {{{{cloze:Context_HTML}}}}
  </div>
  {{{{/Context_HTML}}}}
</div>""".format(type_label=type_label, native_gloss=native_gloss_key)

        afmt = """<div class="card">
  {{{{#Book}}}}
  <div class="source">📚 {{{{Book}}}}</div>
  {{{{/Book}}}}
  
  <div class="type">{type_label}</div>
  <div class="question question--small">{{{{{native_gloss}}}}}</div>
  
  <hr id="answer">
  
  <div class="answer">{{{{{target_lemma}}}}}</div>
  
  {{{{#{target_definition}}}}}
  <div class="definition">{{{{{target_definition}}}}}</div>
  {{{{/{target_definition}}}}}
  
  {{{{#Context_HTML}}}}
  <div class="context">
    <div class="context-label">Kontext:</div>
    {{{{cloze:Context_HTML}}}}
  </div>
  {{{{/Context_HTML}}}}
  
  {{{{#Notes}}}}
  <div class="notes">💡 {{{{Notes}}}}</div>
  {{{{/Notes}}}}
</div>""".format(
            type_label=type_label,
            native_gloss=native_gloss_key,
            target_lemma=target_lemma_key,
            target_definition=target_definition_key,
        )

        css = BASE_CSS + DE_EN_ANSWER_CSS + NIGHT_MODE_CSS
        model_kwargs = {'model_type': genanki.Model.CLOZE}

    else:  # native_native
        model_name = f"Kindle {native_language.upper()}→{native_language.upper()}"
        type_label = f"{native_meta['gemini_label']} → {native_meta['gemini_label']}"
        fields = [
            {'name': native_lemma_key},
            {'name': native_definition_key},
            {'name': 'Context_HTML'},
            {'name': 'Book'},
            {'name': 'Notes'},
        ]

        qfmt = """<div class="card">
  {{{{#Book}}}}
  <div class="source">📚 {{{{Book}}}}</div>
  {{{{/Book}}}}
  
  <div class="type">{type_label}</div>
  <div class="question">{{{{{native_lemma}}}}}</div>
  
  {{{{#Context_HTML}}}}
  <div class="context">
    <div class="context-label">Kontext:</div>
    {{{{Context_HTML}}}}
  </div>
  {{{{/Context_HTML}}}}
</div>""".format(type_label=type_label, native_lemma=native_lemma_key)

        afmt = """<div class="card">
  {{{{#Book}}}}
  <div class="source">📚 {{{{Book}}}}</div>
  {{{{/Book}}}}
  
  <div class="type">{type_label}</div>
  <div class="question question--small">{{{{{native_lemma}}}}}</div>
  
  <hr id="answer">
  
  <div class="answer">{{{{{native_definition}}}}}</div>
  
  {{{{#Context_HTML}}}}
  <div class="context">
    <div class="context-label">Kontext:</div>
    {{{{Context_HTML}}}}
  </div>
  {{{{/Context_HTML}}}}
  
  {{{{#Notes}}}}
  <div class="notes">💡 {{{{Notes}}}}</div>
  {{{{/Notes}}}}
</div>""".format(
            type_label=type_label,
            native_lemma=native_lemma_key,
            native_definition=native_definition_key,
        )

        css = BASE_CSS + DE_DE_ANSWER_CSS + NIGHT_MODE_CSS
        model_kwargs = {}

    templates = [
        {
            'name': deck_type,
            'qfmt': qfmt,
            'afmt': afmt,
        }
    ]

    return genanki.Model(
        model_id,
        model_name,
        fields=fields,
        templates=templates,
        css=css,
        **model_kwargs,
    )


# ============================================================================
# TSV to APKG Conversion
# ============================================================================

def generate_guid_from_lemma(lemma: str, model_id: int, card_type: str = '') -> int:
    """
    Generiert eine eindeutige GUID basierend auf Lemma UND Kartentyp.
    
    WICHTIG: EN→DE und DE→EN müssen unterschiedliche GUIDs haben,
    auch wenn sie dasselbe englische Wort verwenden!
    
    Beim Re-Import werden alte Karten mit gleichem Lemma UND Typ überschrieben,
    aber der Learning-Fortschritt bleibt erhalten!
    
  Args:
    lemma: Das Lemma (erstes Feld der Karte)
    model_id: Die Model-ID
    card_type: Der Kartentyp ('foreign_native', 'native_foreign', 'native_native') für zusätzliche Eindeutigkeit
    
    Returns:
        GUID als Integer
    """
    # Normalisiere Lemma (lowercase, whitespace trimmen)
    normalized_lemma = lemma.strip().lower()
    
    # Erstelle eindeutigen Hash aus Lemma + Model ID + Kartentyp
    # Der Kartentyp stellt sicher, dass EN→DE und DE→EN unterschiedliche GUIDs haben
    hash_str = f"{model_id}_{card_type}_{normalized_lemma}"
    hash_bytes = hashlib.md5(hash_str.encode('utf-8')).digest()
    
    # Konvertiere zu Integer (Anki braucht Integers für GUIDs)
    guid = int.from_bytes(hash_bytes[:8], byteorder='big', signed=True)
    
    return guid


def convert_bold_to_cloze(html: str) -> str:
    """
    Konvertiert <b>word</b> zu {{c1::word}} für Cloze-Karten.

    Für DE→EN Karten: Das englische Wort wird versteckt (cloze),
    damit es nicht gespoilert wird.

    Args:
        html: HTML-String mit <b>word</b> Markierung

    Returns:
        HTML-String mit {{c1::word}} Cloze-Markierung
    """

    if not html:
        return ''

    import re

    # Ersetze <b>...</b> mit {{c1::...}}
    result = re.sub(r'<b>(.*?)</b>', r'{{c1::\1}}', html)
    return result


def convert_cloze_to_bold(html: str) -> str:
    """Konvertiert die erste Cloze-Markierung zurück zu <b>…</b>."""

    if not html:
        return ''

    if '{{c1::' not in html:
        return html

    boldified = html.replace('{{c1::', '<b>', 1)
    return boldified.replace('}}', '</b>', 1)


def read_tsv_file(tsv_path: Path, deck_type: str, native_language: str,
          target_language: str) -> List[List[str]]:
  """Map TSV rows to the field order expected by the Anki models."""

  rows: List[List[str]] = []

  native_language = native_language.lower()
  target_language = target_language.lower()

  native_lemma_key = build_field_key(native_language, 'lemma')
  native_definition_key = build_field_key(native_language, 'definition')
  native_gloss_key = build_field_key(native_language, 'gloss')
  target_lemma_key = build_field_key(target_language, 'lemma')
  target_definition_key = build_field_key(target_language, 'definition')

  with open(tsv_path, 'r', encoding='utf-8') as tsv_file:
    reader = csv.DictReader(tsv_file, delimiter='\t')

    for row_dict in reader:
      context_html = row_dict.get('Context_HTML') or ''

      if deck_type == 'foreign_native':
        prepared_context = convert_cloze_to_bold(context_html)
        row = [
          row_dict.get(target_lemma_key, '') or '',
          row_dict.get(target_definition_key, '') or '',
          row_dict.get(native_gloss_key, '') or '',
          prepared_context,
          row_dict.get('Book', '') or '',
          row_dict.get('Notes', '') or '',
        ]

      elif deck_type == 'native_foreign':
        prepared_context = convert_bold_to_cloze(context_html)
        row = [
          row_dict.get(native_gloss_key, '') or '',
          row_dict.get(target_lemma_key, '') or '',
          row_dict.get(target_definition_key, '') or '',
          prepared_context,
          row_dict.get('Book', '') or '',
          row_dict.get('Notes', '') or '',
        ]

      elif deck_type == 'native_native':
        prepared_context = convert_cloze_to_bold(context_html)
        row = [
          row_dict.get(native_lemma_key, '') or '',
          row_dict.get(native_definition_key, '') or '',
          prepared_context,
          row_dict.get('Book', '') or '',
          row_dict.get('Notes', '') or '',
        ]

      else:
        continue

      rows.append(row)

  return rows


def convert_tsv_to_apkg(tsv_path: Path, output_path: Path, deck_type: str,
                        native_language: str, target_language: str) -> bool:
    """Convert a TSV export into an APKG deck for the requested card orientation."""

    if not tsv_path.exists():
        print(f"❌ TSV-Datei nicht gefunden: {tsv_path}")
        return False

    native_language = native_language.lower()
    target_language = target_language.lower()

    try:
        model = create_model(deck_type, native_language, target_language)
    except ValueError as error:
        print(f"❌ {error}")
        return False

    if deck_type == 'foreign_native':
        deck_name = f"Kindle::{target_language.upper()}→{native_language.upper()}"
    elif deck_type == 'native_foreign':
        deck_name = f"Kindle::{native_language.upper()}→{target_language.upper()}"
    elif deck_type == 'native_native':
        deck_name = f"Kindle::{native_language.upper()}→{native_language.upper()}"
    else:
        print(f"❌ Unbekannter Kartentyp: {deck_type}")
        return False

    rows = read_tsv_file(tsv_path, deck_type, native_language, target_language)

    if not rows:
        print(f"⚠️  TSV-Datei ist leer: {tsv_path}")
        return False

    deck_id = random.randrange(1 << 30, 1 << 31)
    deck = genanki.Deck(deck_id, deck_name)

    for row in rows:
        fields = [str(field) if field else '' for field in row]
        lemma = fields[0]
        guid = generate_guid_from_lemma(lemma, model.model_id, deck_type)

        note = genanki.Note(
            model=model,
            fields=fields,
            guid=guid,
        )
        deck.add_note(note)

    package = genanki.Package(deck)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    package.write_to_file(str(output_path))

    print(f"✅ APKG erstellt: {output_path} ({len(rows)} Karten)")
    return True


def convert_all_tsv_to_apkg(tsv_dir: Path, apkg_dir: Path,
                            native_language: Optional[str] = None,
                            target_language: Optional[str] = None) -> Dict[str, bool]:
    """Convert all known TSV exports for the configured language pair."""

    if native_language is None or target_language is None:
        configured_native, configured_target = validate_language_configuration()
        native_language = native_language or configured_native
        target_language = target_language or configured_target

    native_language = native_language.lower()
    target_language = target_language.lower()

    apkg_dir.mkdir(parents=True, exist_ok=True)

    results: Dict[str, bool] = {}

    pair_foreign_native = format_language_pair(target_language, native_language)
    pair_native_foreign = format_language_pair(native_language, target_language)
    pair_native_native = format_language_pair(native_language, native_language)

    # Foreign → Native
    tsv_path = tsv_dir / f"anki_{pair_foreign_native}.tsv"
    if tsv_path.exists():
        apkg_path = apkg_dir / f"anki_{pair_foreign_native}.apkg"
        success = convert_tsv_to_apkg(
            tsv_path,
            apkg_path,
            'foreign_native',
            native_language,
            target_language,
        )
        results[f"anki_{pair_foreign_native}.tsv → anki_{pair_foreign_native}.apkg"] = success
    else:
        print(f"⏭️  Übersprungen (nicht gefunden): anki_{pair_foreign_native}.tsv")
        results[f"anki_{pair_foreign_native}.tsv"] = False

    # Native → Foreign
    tsv_path = tsv_dir / f"anki_{pair_native_foreign}.tsv"
    if tsv_path.exists():
        apkg_path = apkg_dir / f"anki_{pair_native_foreign}.apkg"
        success = convert_tsv_to_apkg(
            tsv_path,
            apkg_path,
            'native_foreign',
            native_language,
            target_language,
        )
        results[f"anki_{pair_native_foreign}.tsv → anki_{pair_native_foreign}.apkg"] = success
    else:
        print(f"⏭️  Übersprungen (nicht gefunden): anki_{pair_native_foreign}.tsv")
        results[f"anki_{pair_native_foreign}.tsv"] = False

    # Native → Native (monolingual)
    tsv_path = tsv_dir / f"anki_{pair_native_native}.tsv"
    if tsv_path.exists():
        apkg_path = apkg_dir / f"anki_{pair_native_native}.apkg"
        success = convert_tsv_to_apkg(
            tsv_path,
            apkg_path,
            'native_native',
            native_language,
            native_language,
        )
        results[f"anki_{pair_native_native}.tsv → anki_{pair_native_native}.apkg"] = success
    else:
        print(f"⏭️  Übersprungen (nicht gefunden): anki_{pair_native_native}.tsv")
        results[f"anki_{pair_native_native}.tsv"] = False

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
