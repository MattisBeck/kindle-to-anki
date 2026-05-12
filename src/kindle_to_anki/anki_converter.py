"""Convert parsed vocabulary items into Anki cards and APKG packages."""

import hashlib
import html
import random
from dataclasses import asdict
from importlib.resources import files
from pathlib import Path
from typing import cast

import genanki

from kindle_to_anki.models import (
    AnkiCard,
    BaseVocabularyItem,
    ForeignVocabularyItem,
    PromptJob,
    WordRecord,
    normalize_cloze_phrase,
)


DECK_ID_START = 1 << 30
DECK_ID_END = 1 << 31
LOW_CONFIDENCE_THRESHOLD = 0.75
NOTES_SEPARATOR = " | "
GENERIC_DOMAINS = {"", "general", "generic", "allgemein", "neutral", "none", "standard"}
NEUTRAL_FORMALITY = {"", "neutral", "standard", "normal", "allgemein"}
FOREIGN_NATIVE = "foreign_native"
NATIVE_FOREIGN = "native_foreign"
NATIVE_NATIVE = "native_native"
# Keep these field names stable. Anki matches imported notes by model fields and GUID
MODEL_FIELDS = [
    "Lemma",
    "OriginalWord",
    "Definition",
    "Gloss",
    "Context",
    "Book",
    "Notes",
]
CARD_TYPE_LABELS = {
    FOREIGN_NATIVE: "Foreign Vocabulary Card",
    NATIVE_FOREIGN: "Reverse Vocabulary Card",
    NATIVE_NATIVE: "Native Vocabulary Definition",
}
# Each card type shares the same fields, but uses its own front/back templates and accent color
CARD_TYPE_TEMPLATES = {
    FOREIGN_NATIVE: (
        "foreign_native_front.html",
        "foreign_native_back.html",
        "answer_foreign.css",
    ),
    NATIVE_FOREIGN: (
        "native_foreign_front.html",
        "native_foreign_back.html",
        "answer_reverse.css",
    ),
    NATIVE_NATIVE: (
        "native_native_front.html",
        "native_native_back.html",
        "answer_native.css",
    ),
}


def load_template(filename: str) -> str:
    """
    Loads an Anki HTML or CSS template from the package templates directory.
    :param filename: Template file name
    :return: Template contents
    """
    return files("kindle_to_anki").joinpath("templates", filename).read_text(encoding="utf-8")


def get_language_pair(source_language_code: str, native_language_code: str) -> str:
    """
    Builds the canonical language pair key for Anki cards.
    :param source_language_code: Language code of the Kindle vocabulary item
    :param native_language_code: Language code of the user's native language
    :return: Language pair string, e.g. "en_de"
    """
    return f"{source_language_code.lower()}_{native_language_code.lower()}"


def build_notes(item: BaseVocabularyItem) -> str:
    """
    Builds a concise notes string from optional Gemini response metadata.
    :param item: Parsed Gemini vocabulary item
    :return: Notes string for the Anki card
    """
    notes: list[str] = []
    if item.false_friend:
        false_friend_note = item.false_friend_note or "False friend"
        notes.append(f"False friend: {false_friend_note}")
    if item.notes:
        notes.append(item.notes)
    if item.ambiguity in {"medium", "high"} and item.sense:
        notes.append(f"Sense: {item.sense}")
    if item.domain.lower() not in GENERIC_DOMAINS:
        notes.append(f"Domain: {item.domain}")
    if item.formality.lower() not in NEUTRAL_FORMALITY:
        notes.append(f"Formality: {item.formality}")
    if item.alternatives:
        notes.append(f"Alternatives: {', '.join(item.alternatives)}")
    if item.collocations:
        notes.append(f"Collocations: {', '.join(item.collocations)}")
    if item.confidence < LOW_CONFIDENCE_THRESHOLD:
        notes.append(f"Low confidence: {item.confidence:.2f}")
    return NOTES_SEPARATOR.join(notes)


def highlight_context(context: str, anchor: str) -> str:
    """
    Escapes context text and highlights the first matching anchor.
    :param context: Kindle context sentence or passage
    :param anchor: Short Gemini anchor identifying the relevant usage
    :return: HTML-safe context with the first anchor wrapped in bold tags
    """
    escaped_context = html.escape(context)
    escaped_anchor = html.escape(anchor.strip())
    if not escaped_anchor or escaped_anchor not in escaped_context:
        return escaped_context
    return escaped_context.replace(escaped_anchor, f"<b>{escaped_anchor}</b>", 1)


def cloze_context(context: str, cloze_text: str) -> str:
    """
    Escapes context text and hides the requested text as a cloze.
    :param context: Kindle context sentence or passage
    :param cloze_text: Exact text to hide
    :return: HTML-safe context with a cloze deletion around the requested text
    """
    escaped_context = html.escape(context)
    escaped_cloze_text = html.escape(cloze_text.strip())
    if escaped_cloze_text and escaped_cloze_text in escaped_context:
        return escaped_context.replace(escaped_cloze_text, f"{{{{c1::{escaped_cloze_text}}}}}", 1)
    return escaped_context


def prompt_jobs_to_anki_cards(prompts: dict[str, list[PromptJob]]) -> dict[str, list[AnkiCard]]:
    """
    Converts processed prompt jobs to AnkiCard objects grouped by language pair.
    :param prompts: Dictionary of prompt jobs after Gemini processing
    :return: Dictionary mapping language pair keys to AnkiCard lists
    """
    cards_by_language_pair: dict[str, list[AnkiCard]] = {}
    for prompt_group in prompts.values():
        for job in prompt_group:
            # Only processed jobs have the validated Gemini response needed for card creation
            if job.parsed_response is None:
                continue
            language_pair = get_language_pair(job.source_language_code, job.native_language_code)
            items = cast(list[BaseVocabularyItem], job.parsed_response.items)
            for item in items:
                # Gemini item indices point back to the original WordRecord in the prompt batch.
                cards_by_language_pair.setdefault(language_pair, []).append(
                    vocabulary_item_to_anki_card(job, item, job.words[item.item_index], language_pair)
                )
                if isinstance(item, ForeignVocabularyItem):
                    reverse_language_pair = get_language_pair(job.native_language_code, job.source_language_code)
                    cards_by_language_pair.setdefault(reverse_language_pair, []).append(
                        vocabulary_item_to_reverse_anki_card(
                            job,
                            item,
                            job.words[item.item_index],
                            reverse_language_pair,
                        )
                    )
    return cards_by_language_pair


def vocabulary_item_to_anki_card(
    job: PromptJob,
    item: BaseVocabularyItem,
    word: WordRecord,
    language_pair: str,
) -> AnkiCard:
    """
    Converts one parsed vocabulary item to an AnkiCard.
    :param job: Prompt job that produced the item
    :param item: Parsed Gemini vocabulary item
    :param word: Original Kindle word record referenced by the item
    :param language_pair: Canonical language pair key
    :return: Prepared Anki card
    """
    gloss = item.gloss if isinstance(item, ForeignVocabularyItem) else ""
    return AnkiCard(
        language_pair=language_pair,
        source_language_code=job.source_language_code,
        native_language_code=job.native_language_code,
        lemma=item.lemma,
        original_word=word.word,
        definition=item.definition,
        gloss=gloss,
        context_html=highlight_context(word.context, item.anchor),
        book_title=word.origin.title,
        book_authors=word.origin.authors,
        notes=build_notes(item),
        guid_key=f"{language_pair}:{word.stem}",
    )


def vocabulary_item_to_reverse_anki_card(
    job: PromptJob,
    item: ForeignVocabularyItem,
    word: WordRecord,
    language_pair: str,
) -> AnkiCard:
    """
    Converts one foreign vocabulary item to a reverse AnkiCard.
    :param job: Prompt job that produced the item
    :param item: Parsed foreign vocabulary item
    :param word: Original Kindle word record referenced by the item
    :param language_pair: Canonical reverse language pair key
    :return: Prepared reverse Anki card
    """
    return AnkiCard(
        language_pair=language_pair,
        source_language_code=job.source_language_code,
        native_language_code=job.native_language_code,
        lemma=item.lemma,
        original_word=word.word,
        definition=item.definition,
        gloss=item.gloss,
        context_html=cloze_context(
            word.context,
            normalize_cloze_phrase(item.cloze_phrase, word.context, word.word) or word.word,
        ),
        book_title=word.origin.title,
        book_authors=word.origin.authors,
        notes=build_notes(item),
        guid_key=f"{language_pair}:{word.stem}",
    )


def anki_cards_to_dict(cards_by_language_pair: dict[str, list[AnkiCard]]) -> dict[str, list[dict]]:
    """
    Converts AnkiCard objects to JSON-compatible dictionaries.
    :param cards_by_language_pair: Dictionary mapping language pair keys to AnkiCard lists
    :return: JSON-compatible card dictionary
    """
    return {
        language_pair: [asdict(card) for card in cards]
        for language_pair, cards in cards_by_language_pair.items()
    }


def anki_cards_from_dict(card_dict: dict[str, list[dict]]) -> dict[str, list[AnkiCard]]:
    """
    Converts JSON-compatible dictionaries to AnkiCard objects.
    :param card_dict: Dictionary mapping language pair keys to serialized AnkiCard dictionaries
    :return: Dictionary mapping language pair keys to AnkiCard lists
    """
    return {
        language_pair: [AnkiCard(**card) for card in cards]
        for language_pair, cards in card_dict.items()
    }


def get_card_type(card: AnkiCard) -> str:
    """
    Determines the Anki card type from source and native language.
    :param card: Prepared Anki card data
    :return: Card type identifier
    """
    if card.source_language_code.lower() == card.native_language_code.lower():
        return NATIVE_NATIVE
    if card.language_pair.lower() == get_language_pair(card.native_language_code, card.source_language_code):
        return NATIVE_FOREIGN
    return FOREIGN_NATIVE


def get_model_id(card_type: str) -> int:
    """
    Builds a stable genanki model ID for one card type.
    :param card_type: Card type identifier
    :return: Stable model ID
    """
    # Stable model IDs keep Anki from creating new note types on every export
    digest = hashlib.md5(f"Kindle Vocabulary:{card_type}".encode("utf-8")).digest()
    return int.from_bytes(digest[:4], byteorder="big") & 0x7FFFFFFF


def get_type_label(card_type: str) -> str:
    """
    Builds a short label shown on the Anki card.
    :param card_type: Card type identifier
    :return: Human-readable card type label
    """
    return CARD_TYPE_LABELS.get(card_type, CARD_TYPE_LABELS[FOREIGN_NATIVE])


def create_anki_model(card_type: str = FOREIGN_NATIVE) -> genanki.Model:
    """
    Creates the genanki note model used for generated Kindle vocabulary cards.
    :param card_type: Card type identifier used to select HTML and CSS templates
    :return: genanki model with stable field names and simple front/back templates
    """
    front_template, back_template, answer_css = CARD_TYPE_TEMPLATES.get(
        card_type,
        CARD_TYPE_TEMPLATES[FOREIGN_NATIVE],
    )
    type_label = get_type_label(card_type)

    model_kwargs = {"model_type": genanki.Model.CLOZE} if card_type == NATIVE_FOREIGN else {}

    return genanki.Model(
        get_model_id(card_type),
        f"Kindle Vocabulary {card_type}",
        fields=[{"name": field} for field in MODEL_FIELDS],
        templates=[
            {
                "name": "Vocabulary",
                "qfmt": load_template(front_template).format(type_label=type_label),
                "afmt": load_template(back_template).format(type_label=type_label),
            }
        ],
        css=(
            load_template("base.css")
            + load_template(answer_css)
            + load_template("night_mode.css")
        ),
        **model_kwargs,
    )


def get_card_guid(guid_key: str) -> str:
    """
    Builds a stable genanki GUID from a card key.
    :param guid_key: Stable card key, usually language pair and normalized stem
    :return: Stable GUID string
    """
    # Stable GUIDs let Anki update duplicate notes instead of importing new copies
    return hashlib.sha256(guid_key.encode("utf-8")).hexdigest()


def format_book(card: AnkiCard) -> str:
    """
    Formats book metadata for the Anki note.
    :param card: Prepared Anki card data
    :return: Book title with author when available
    """
    if card.book_authors:
        return f"{card.book_title} - {card.book_authors}"
    return card.book_title


def anki_card_to_note(card: AnkiCard, model: genanki.Model) -> genanki.Note:
    """
    Converts one AnkiCard to a genanki note.
    :param card: Prepared Anki card data
    :param model: genanki model used by the note
    :return: genanki note
    """
    return genanki.Note(
        model=model,
        fields=[
            card.lemma,
            card.original_word,
            card.definition,
            card.gloss,
            card.context_html,
            format_book(card),
            card.notes,
        ],
        guid=get_card_guid(card.guid_key),
    )


def write_apkg(cards: list[AnkiCard], output_path: Path, deck_name: str) -> None:
    """
    Writes Anki cards to an APKG file.
    :param cards: Prepared Anki card data
    :param output_path: Target APKG path
    :param deck_name: Name of the Anki deck
    :return: None
    """
    if not cards:
        raise ValueError("Cannot write an Anki deck without cards")
    card_type = get_card_type(cards[0])
    model = create_anki_model(card_type)
    deck = genanki.Deck(random.randrange(DECK_ID_START, DECK_ID_END), deck_name)
    for card in cards:
        deck.add_note(anki_card_to_note(card, model))
    output_path.parent.mkdir(parents=True, exist_ok=True)
    genanki.Package(deck).write_to_file(str(output_path))
