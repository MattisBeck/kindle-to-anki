"""Export utilities for creating TSV and APKG files."""

from pathlib import Path
from typing import Dict, List

from .helpers import build_field_key, format_language_pair


def _sanitize_tsv_value(value: str, newline_replacement: str = ' ') -> str:
    """Normalize fields so TSV rows never contain raw tabs or newlines."""

    if value is None:
        return ''

    text = str(value)
    text = text.replace('\r\n', '\n').replace('\r', '\n')
    text = text.replace('\t', ' ')
    return text.replace('\n', newline_replacement)


def _ensure_bold_context(card: Dict) -> str:
    """Return context HTML with bold markup even if cache contains cloze tags."""

    context_html = card.get('Context_HTML', '')

    if '{{c1::' not in context_html:
        return context_html

    # Older cache entries may store cloze markup; convert the first occurrence back to <b>…</b>
    boldified = context_html.replace('{{c1::', '<b>', 1)
    return boldified.replace('}}', '</b>', 1)


def _ensure_cloze_context(card: Dict) -> str:
    """Return context HTML with cloze markup for DE→EN cards."""

    context_html = card.get('Context_HTML', '')

    # If already cloze, return as-is
    if '{{c1::' in context_html:
        return context_html

    # If bold, convert to cloze
    if '<b>' in context_html:
        clozified = context_html.replace('<b>', '{{c1::', 1)
        return clozified.replace('</b>', '}}', 1)

    return context_html


def create_tsv_file(cards: List[Dict], output_file: str, card_type: str,
                    native_language: str, target_language: str,
                    verbose: bool = False):
    """Create a TSV file ready for Anki import."""

    if not cards:
        if verbose:
            print(f"  ⚠️  No cards to export for {card_type}")
        return

    output_path = Path(output_file)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    native_language = native_language.lower()
    target_language = target_language.lower()

    native_lemma_key = build_field_key(native_language, 'lemma')
    native_definition_key = build_field_key(native_language, 'definition')
    native_gloss_key = build_field_key(native_language, 'gloss')
    target_lemma_key = build_field_key(target_language, 'lemma')
    target_definition_key = build_field_key(target_language, 'definition')

    if card_type == 'native_native':
        header = f"{native_lemma_key}\tOriginal_word\t{native_definition_key}\tContext_HTML\tBook\tNotes\n"
        context_transform = _ensure_bold_context
    elif card_type == 'foreign_native':
        header = f"{target_lemma_key}\tOriginal_word\t{target_definition_key}\t{native_gloss_key}\tContext_HTML\tBook\tNotes\n"
        context_transform = _ensure_bold_context
    else:  # native_foreign
        header = f"{native_gloss_key}\t{target_lemma_key}\tOriginal_word\t{target_definition_key}\tContext_HTML\tBook\tNotes\n"
        context_transform = _ensure_cloze_context

    lines = [header]

    for card in cards:
        notes = _sanitize_tsv_value(card.get('Notes', ''), newline_replacement=' ')
        context_html = _sanitize_tsv_value(context_transform(card), newline_replacement='<br>')
        book = _sanitize_tsv_value(card.get('Book', ''), newline_replacement=' ')

        if card_type == 'native_native':
            line = f"{_sanitize_tsv_value(card.get(native_lemma_key, ''))}\t"
            line += f"{_sanitize_tsv_value(card.get('Original_word', ''))}\t"
            line += f"{_sanitize_tsv_value(card.get(native_definition_key, ''))}\t"
            line += f"{context_html}\t"
            line += f"{book}\t"
            line += f"{notes}\n"

        elif card_type == 'foreign_native':
            line = f"{_sanitize_tsv_value(card.get(target_lemma_key, ''))}\t"
            line += f"{_sanitize_tsv_value(card.get('Original_word', ''))}\t"
            line += f"{_sanitize_tsv_value(card.get(target_definition_key, ''))}\t"
            line += f"{_sanitize_tsv_value(card.get(native_gloss_key, ''))}\t"
            line += f"{context_html}\t"
            line += f"{book}\t"
            line += f"{notes}\n"

        else:  # native_foreign
            line = f"{_sanitize_tsv_value(card.get(native_gloss_key, ''))}\t"
            line += f"{_sanitize_tsv_value(card.get(target_lemma_key, ''))}\t"
            line += f"{_sanitize_tsv_value(card.get('Original_word', ''))}\t"
            line += f"{_sanitize_tsv_value(card.get(target_definition_key, ''))}\t"
            line += f"{context_html}\t"
            line += f"{book}\t"
            line += f"{notes}\n"

        lines.append(line)

    try:
        with open(output_file, 'w', encoding='utf-8') as tsv_file:
            tsv_file.writelines(lines)

        if verbose:
            print(f"  ✅ TSV created: {output_file} ({len(cards)} cards)")
    except Exception as exc:  # pragma: no cover - best-effort logging
        if verbose:
            print(f"  ❌ TSV creation failed: {exc}")


def create_all_tsv_files(foreign_cards: List[Dict], native_cards: List[Dict],
                         native_language: str, target_language: str,
                         verbose: bool = False):
    """
    Create all TSV files (EN→DE, DE→EN, DE→DE)
    
    Args:
        en_cards: List of English cards
        de_cards: List of German cards
        verbose: Enable verbose output
    """
    from .config import CONFIG
    
    tsv_dir = Path(CONFIG['TSV_OUTPUT_DIR'])
    tsv_dir.mkdir(parents=True, exist_ok=True)

    create_foreign_native = CONFIG.get('CREATE_FOREIGN_TO_NATIVE', True)
    create_native_foreign = CONFIG.get('CREATE_NATIVE_TO_FOREIGN', True)
    create_native_native = CONFIG.get('CREATE_NATIVE_TO_NATIVE', True)

    pair_foreign_native = format_language_pair(target_language, native_language)
    pair_native_foreign = format_language_pair(native_language, target_language)
    pair_native_native = format_language_pair(native_language, native_language)

    # Foreign → Native deck
    if foreign_cards and create_foreign_native:
        output_file = tsv_dir / f"anki_{pair_foreign_native}.tsv"
        create_tsv_file(
            foreign_cards,
            str(output_file),
            'foreign_native',
            native_language,
            target_language,
            verbose,
        )

    # Native → Foreign deck (reverse cards)
    if foreign_cards and create_native_foreign:
        output_file = tsv_dir / f"anki_{pair_native_foreign}.tsv"
        create_tsv_file(
            foreign_cards,
            str(output_file),
            'native_foreign',
            native_language,
            target_language,
            verbose,
        )

    # Native → Native deck (monolingual)
    if native_cards and create_native_native:
        output_file = tsv_dir / f"anki_{pair_native_native}.tsv"
        create_tsv_file(
            native_cards,
            str(output_file),
            'native_native',
            native_language,
            target_language,
            verbose,
        )


def export_to_apkg(tsv_dir: str, apkg_dir: str, verbose: bool = False):
    """
    Convert all TSV files to APKG format using apkg_builder module
    
    Args:
        tsv_dir: Directory containing TSV files
        apkg_dir: Output directory for APKG files
        verbose: Enable verbose output
    """
    try:
        from pathlib import Path
        from .apkg_builder import convert_all_tsv_to_apkg
        
        # Convert all TSV files
        if verbose:
            print("\n📦 Converting TSV to APKG...")
        
        convert_all_tsv_to_apkg(Path(tsv_dir), Path(apkg_dir))
        
        if verbose:
            print("✅ APKG export complete")
    
    except ImportError as e:
        if verbose:
            print(f"⚠️  APKG export skipped: apkg_builder module not found ({e})")
    except Exception as e:
        if verbose:
            print(f"❌ APKG export failed: {e}")


def remove_duplicates(cards: List[Dict], language: str) -> List[Dict]:
    """
    Remove duplicate cards based on lemma field
    
    Args:
    cards: List of card dictionaries
    language: ISO code used for the lemma field
        
    Returns:
        Deduplicated list of cards
    """
    seen = set()
    unique_cards = []
    
    # Determine lemma key based on language
    lemma_key = build_field_key(language.lower(), 'lemma')
    
    for card in cards:
        value = card.get(lemma_key, '').lower()
        if value and value not in seen:
            seen.add(value)
            unique_cards.append(card)
    
    return unique_cards


def validate_card(card: Dict, card_type: str,
                  native_language: str, target_language: str) -> bool:
    """
    Validate card has required fields
    
    Args:
    card: Card dictionary
    card_type: 'foreign_native', 'native_foreign', or 'native_native'
        
    Returns:
        True if card is valid
    """
    native_language = native_language.lower()
    target_language = target_language.lower()

    native_lemma_key = build_field_key(native_language, 'lemma')
    native_definition_key = build_field_key(native_language, 'definition')
    native_gloss_key = build_field_key(native_language, 'gloss')
    target_lemma_key = build_field_key(target_language, 'lemma')
    target_definition_key = build_field_key(target_language, 'definition')

    if card_type == 'native_native':
        required_fields = [native_lemma_key, 'Original_word', native_definition_key, 'Context_HTML', 'Book']
    elif card_type == 'foreign_native':
        required_fields = [target_lemma_key, 'Original_word', target_definition_key, native_gloss_key, 'Context_HTML', 'Book']
    else:  # native_foreign
        required_fields = [native_gloss_key, target_lemma_key, 'Original_word', target_definition_key, 'Context_HTML', 'Book']
    
    # Check all required fields exist and are non-empty
    for field in required_fields:
        if not card.get(field):
            return False
    
    return True


def filter_valid_cards(cards: List[Dict], card_type: str,
                       native_language: str, target_language: str,
                       verbose: bool = False) -> List[Dict]:
    """
    Filter out invalid cards
    
    Args:
    cards: List of card dictionaries
    card_type: 'foreign_native', 'native_foreign', or 'native_native'
        verbose: Enable verbose output
        
    Returns:
        List of valid cards
    """
    valid_cards = [
        card for card in cards
    if validate_card(card, card_type, native_language, target_language)
    ]
    
    if verbose and len(valid_cards) < len(cards):
        invalid_count = len(cards) - len(valid_cards)
        print(f"  ⚠️  Filtered out {invalid_count} invalid cards")
    
    return valid_cards
