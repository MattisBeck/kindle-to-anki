"""Export utilities for creating TSV and APKG files."""

from pathlib import Path
from typing import List, Dict


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


def create_tsv_file(cards: List[Dict], output_file: str, card_type: str, verbose: bool = False):
    """Create a TSV file ready for Anki import."""

    if not cards:
        if verbose:
            print(f"  ⚠️  No cards to export for {card_type}")
        return

    output_path = Path(output_file)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    if card_type == 'de_de':
        header = "DE_lemma\tOriginal_word\tDE_definition\tContext_HTML\tBook\tNotes\n"
    elif card_type == 'en_de':
        header = "EN_lemma\tOriginal_word\tEN_definition\tDE_gloss\tContext_HTML\tBook\tNotes\n"
    else:  # de_en
        header = "DE_gloss\tEN_lemma\tOriginal_word\tEN_definition\tContext_HTML\tBook\tNotes\n"

    lines = [header]

    for card in cards:
        notes = card.get('Notes', '')
        
        # For DE→EN, use cloze; for EN→DE and DE→DE, use bold
        if card_type == 'de_en':
            context_html = _ensure_cloze_context(card)
        else:
            context_html = _ensure_bold_context(card)

        if card_type == 'de_de':
            line = f"{card.get('DE_lemma', '')}\t"
            line += f"{card.get('Original_word', '')}\t"
            line += f"{card.get('DE_definition', '')}\t"
            line += f"{context_html}\t"
            line += f"{card.get('Book', '')}\t"
            line += f"{notes}\n"

        elif card_type == 'en_de':
            line = f"{card.get('EN_lemma', '')}\t"
            line += f"{card.get('Original_word', '')}\t"
            line += f"{card.get('EN_definition', '')}\t"
            line += f"{card.get('DE_gloss', '')}\t"
            line += f"{context_html}\t"
            line += f"{card.get('Book', '')}\t"
            line += f"{notes}\n"

        else:  # de_en
            line = f"{card.get('DE_gloss', '')}\t"
            line += f"{card.get('EN_lemma', '')}\t"
            line += f"{card.get('Original_word', '')}\t"
            line += f"{card.get('EN_definition', '')}\t"
            line += f"{context_html}\t"  # Already has cloze from _ensure_cloze_context
            line += f"{card.get('Book', '')}\t"
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


def create_all_tsv_files(en_cards: List[Dict], de_cards: List[Dict], verbose: bool = False):
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
    
    # EN → DE cards (English word → German translation)
    if en_cards:
        output_file = tsv_dir / 'anki_en_de.tsv'
        create_tsv_file(en_cards, str(output_file), 'en_de', verbose)
    
    # DE → EN cards (German translation → English word) - REVERSE of EN→DE!
    # WICHTIG: Verwendet en_cards, nicht de_cards!
    if en_cards:
        output_file = tsv_dir / 'anki_de_en.tsv'
        create_tsv_file(en_cards, str(output_file), 'de_en', verbose)
    
    # DE → DE cards (German word → German definition)
    if de_cards:
        output_file = tsv_dir / 'anki_de_de.tsv'
        create_tsv_file(de_cards, str(output_file), 'de_de', verbose)


def export_to_apkg(tsv_dir: str, apkg_dir: str, verbose: bool = False):
    """
    Convert all TSV files to APKG format using tsv_to_apkg.py
    
    Args:
        tsv_dir: Directory containing TSV files
        apkg_dir: Output directory for APKG files
        verbose: Enable verbose output
    """
    try:
        # Import the converter module
        import sys
        from pathlib import Path
        
        # Add parent directory to path
        script_dir = Path(__file__).parent.parent
        if str(script_dir) not in sys.path:
            sys.path.insert(0, str(script_dir))
        
        from tsv_to_apkg import convert_all_tsv_to_apkg
        
        # Convert all TSV files (without verbose parameter)
        if verbose:
            print("\n📦 Converting TSV to APKG...")
        
        convert_all_tsv_to_apkg(Path(tsv_dir), Path(apkg_dir))
        
        if verbose:
            print("✅ APKG export complete")
    
    except ImportError as e:
        if verbose:
            print(f"⚠️  APKG export skipped: tsv_to_apkg.py not found ({e})")
    except Exception as e:
        if verbose:
            print(f"❌ APKG export failed: {e}")


def remove_duplicates(cards: List[Dict], language: str = 'en') -> List[Dict]:
    """
    Remove duplicate cards based on lemma field
    
    Args:
        cards: List of card dictionaries
        language: 'en' or 'de' to determine which lemma field to use
        
    Returns:
        Deduplicated list of cards
    """
    seen = set()
    unique_cards = []
    
    # Determine lemma key based on language
    lemma_key = 'EN_lemma' if language == 'en' else 'DE_lemma'
    
    for card in cards:
        value = card.get(lemma_key, '').lower()
        if value and value not in seen:
            seen.add(value)
            unique_cards.append(card)
    
    return unique_cards


def validate_card(card: Dict, card_type: str) -> bool:
    """
    Validate card has required fields
    
    Args:
        card: Card dictionary
        card_type: 'en_de', 'de_en', or 'de_de'
        
    Returns:
        True if card is valid
    """
    if card_type == 'de_de':
        required_fields = ['DE_lemma', 'Original_word', 'DE_definition', 'Context_HTML', 'Book']
    elif card_type == 'en_de':
        required_fields = ['EN_lemma', 'Original_word', 'EN_definition', 'DE_gloss', 'Context_HTML', 'Book']
    else:  # de_en
        required_fields = ['DE_gloss', 'EN_lemma', 'Original_word', 'EN_definition', 'Context_HTML', 'Book']
    
    # Check all required fields exist and are non-empty
    for field in required_fields:
        if not card.get(field):
            return False
    
    return True


def filter_valid_cards(cards: List[Dict], card_type: str, verbose: bool = False) -> List[Dict]:
    """
    Filter out invalid cards
    
    Args:
        cards: List of card dictionaries
        card_type: 'en_de', 'de_en', or 'de_de'
        verbose: Enable verbose output
        
    Returns:
        List of valid cards
    """
    valid_cards = [card for card in cards if validate_card(card, card_type)]
    
    if verbose and len(valid_cards) < len(cards):
        invalid_count = len(cards) - len(valid_cards)
        print(f"  ⚠️  Filtered out {invalid_count} invalid cards")
    
    return valid_cards
