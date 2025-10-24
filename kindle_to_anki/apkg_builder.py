"""
APKG Builder Module
Creates Anki APKG packages from TSV files with custom card templates
"""

import genanki
import csv
from pathlib import Path
from typing import Dict, List, Optional
import random
import hashlib

try:
    from importlib.resources import files
except ImportError:
    # Python < 3.9 fallback
    from importlib_resources import files  # type: ignore

from .helpers import (
    build_field_key,
    format_language_pair,
    get_language_meta,
    validate_language_configuration,
)

# ============================================================================
# Template Loading
# ============================================================================

def load_template(filename: str) -> str:
    """Load a template file from the templates directory."""
    try:
        template_path = files(__package__).joinpath('templates', filename)
        return template_path.read_text(encoding='utf-8')
    except Exception as e:
        raise RuntimeError(f"Failed to load template '{filename}': {e}")


def load_css() -> Dict[str, str]:
    """Load all CSS templates."""
    return {
        'base': load_template('base.css'),
        'night_mode': load_template('night_mode.css'),
        'answer_blue': load_template('answer_blue.css'),
        'answer_red': load_template('answer_red.css'),
        'answer_teal': load_template('answer_teal.css'),
    }


def load_html_templates() -> Dict[str, str]:
    """Load all HTML templates."""
    return {
        'foreign_native_front': load_template('foreign_native_front.html'),
        'foreign_native_back': load_template('foreign_native_back.html'),
        'native_foreign_front': load_template('native_foreign_front.html'),
        'native_foreign_back': load_template('native_foreign_back.html'),
        'native_native_front': load_template('native_native_front.html'),
        'native_native_back': load_template('native_native_back.html'),
    }


# Load templates once at module level
CSS_TEMPLATES = load_css()
HTML_TEMPLATES = load_html_templates()

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

        qfmt = HTML_TEMPLATES['foreign_native_front'].format(
            type_label=type_label,
            target_lemma=target_lemma_key
        )

        afmt = HTML_TEMPLATES['foreign_native_back'].format(
            type_label=type_label,
            target_lemma=target_lemma_key,
            native_gloss=native_gloss_key,
            target_definition=target_definition_key,
        )

        css = CSS_TEMPLATES['base'] + CSS_TEMPLATES['answer_blue'] + CSS_TEMPLATES['night_mode']
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

        qfmt = HTML_TEMPLATES['native_foreign_front'].format(
            type_label=type_label,
            native_gloss=native_gloss_key
        )

        afmt = HTML_TEMPLATES['native_foreign_back'].format(
            type_label=type_label,
            native_gloss=native_gloss_key,
            target_lemma=target_lemma_key,
            target_definition=target_definition_key,
        )

        css = CSS_TEMPLATES['base'] + CSS_TEMPLATES['answer_red'] + CSS_TEMPLATES['night_mode']
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

        qfmt = HTML_TEMPLATES['native_native_front'].format(
            type_label=type_label,
            native_lemma=native_lemma_key
        )

        afmt = HTML_TEMPLATES['native_native_back'].format(
            type_label=type_label,
            native_lemma=native_lemma_key,
            native_definition=native_definition_key,
        )

        css = CSS_TEMPLATES['base'] + CSS_TEMPLATES['answer_teal'] + CSS_TEMPLATES['night_mode']
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
