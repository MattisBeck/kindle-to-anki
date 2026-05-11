from pathlib import Path

import pytest

from kindle_to_anki.anki_converter import (
    anki_card_to_note,
    anki_cards_from_dict,
    anki_cards_to_dict,
    build_notes,
    cloze_context,
    create_anki_model,
    format_book,
    get_card_guid,
    get_card_type,
    get_language_pair,
    highlight_context,
    load_template,
    NATIVE_FOREIGN,
    NATIVE_NATIVE,
    prompt_jobs_to_anki_cards,
    write_apkg,
)
from kindle_to_anki.models import (
    AnkiCard,
    ForeignVocabularyBatch,
    NativeDefinitionBatch,
    PromptJob,
    PromptType,
    SourceBook,
    WordRecord,
)


def test_get_language_pair() -> None:
    assert get_language_pair("en", "de") == "en_de"


def test_load_template() -> None:
    assert "card" in load_template("foreign_native_front.html")


def test_build_notes() -> None:
    item = ForeignVocabularyBatch.model_validate_json("""
    {
        "items": [
            {
                "item_index": 0,
                "lemma": "eventually",
                "definition": "at a later time",
                "ambiguity": "high",
                "sense": "later, not possibly",
                "domain": "general",
                "formality": "neutral",
                "alternatives": ["ultimately", "finally"],
                "collocations": ["eventually become"],
                "false_friend": true,
                "false_friend_note": "Not German eventuell.",
                "anchor": "eventually",
                "confidence": 0.7,
                "gloss": "schliesslich"
            }
        ]
    }
    """).items[0]

    notes = build_notes(item)

    assert "False friend: Not German eventuell." in notes
    assert "Sense: later, not possibly" in notes
    assert "Alternatives: ultimately, finally" in notes
    assert "Collocations: eventually become" in notes
    assert "Low confidence: 0.70" in notes
    assert "Domain" not in notes
    assert "Formality" not in notes


def test_highlight_context() -> None:
    context = "The <alarm> kept reverberating."

    highlighted = highlight_context(context, "reverberating")

    assert highlighted == "The &lt;alarm&gt; kept <b>reverberating</b>."


def test_cloze_context() -> None:
    context = "Low clouds moved across the ridge."

    clozed_context = cloze_context(context, "clouds")

    assert clozed_context == "Low {{c1::clouds}} moved across the ridge."


def test_cloze_context_uses_fallback_word() -> None:
    context = "Low clouds moved across the ridge."

    clozed_context = cloze_context(context, "cloud", "clouds")

    assert clozed_context == "Low {{c1::clouds}} moved across the ridge."


def test_prompt_jobs_to_anki_cards_foreign() -> None:
    book = SourceBook("Broken Orbit", "Evan Shore")
    word = WordRecord("clouds", "en", "cloud", "Low clouds moved across the ridge.", book)
    batch = ForeignVocabularyBatch.model_validate_json("""
    {
        "items": [
            {
                "item_index": 0,
                "lemma": "cloud",
                "definition": "a visible mass of condensed water vapor",
                "ambiguity": "low",
                "anchor": "clouds",
                "confidence": 1.0,
                "gloss": "Wolke"
            }
        ]
    }
    """)
    prompt_job = PromptJob("", PromptType.FOREIGN_VOCABULARY, [word], "de", "en", parsed_response=batch)

    cards_by_language_pair = prompt_jobs_to_anki_cards({"en": [prompt_job]})

    card = cards_by_language_pair["en_de"][0]
    assert card.language_pair == "en_de"
    assert card.lemma == "cloud"
    assert card.original_word == "clouds"
    assert card.gloss == "Wolke"
    assert card.definition == "a visible mass of condensed water vapor"
    assert card.context_html == "Low <b>clouds</b> moved across the ridge."
    assert card.book_title == "Broken Orbit"
    assert card.guid_key == "en_de:cloud"

    reverse_card = cards_by_language_pair["de_en"][0]
    assert reverse_card.language_pair == "de_en"
    assert reverse_card.lemma == "cloud"
    assert reverse_card.gloss == "Wolke"
    assert reverse_card.context_html == "Low {{c1::clouds}} moved across the ridge."
    assert reverse_card.guid_key == "de_en:cloud"


def test_prompt_jobs_to_anki_cards_native() -> None:
    book = SourceBook("Gewohnheiten im Alltag", "Martin Keller")
    word = WordRecord("Bug", "de", "Bug", "Das war ein Bug.", book)
    batch = NativeDefinitionBatch.model_validate_json("""
    {
        "items": [
            {
                "item_index": 0,
                "lemma": "Bug",
                "definition": "Ein Fehler in einem Computerprogramm.",
                "ambiguity": "low",
                "anchor": "Bug",
                "confidence": 1.0
            }
        ]
    }
    """)
    prompt_job = PromptJob("", PromptType.NATIVE_DEFINITION, [word], "de", "de", parsed_response=batch)

    cards_by_language_pair = prompt_jobs_to_anki_cards({"de": [prompt_job]})

    card = cards_by_language_pair["de_de"][0]
    assert card.gloss == ""
    assert card.definition == "Ein Fehler in einem Computerprogramm."


def test_prompt_jobs_to_anki_cards_skips_unprocessed_jobs() -> None:
    prompt_job = PromptJob("", PromptType.NATIVE_DEFINITION, [], "de", "de")

    assert prompt_jobs_to_anki_cards({"de": [prompt_job]}) == {}


def test_anki_cards_json_roundtrip() -> None:
    card = AnkiCard(
        language_pair="en_de",
        source_language_code="en",
        native_language_code="de",
        lemma="cloud",
        original_word="clouds",
        definition="a visible mass of condensed water vapor",
        gloss="Wolke",
        context_html="Low <b>clouds</b> moved across the ridge.",
        book_title="Broken Orbit",
        book_authors="Evan Shore",
        notes="",
        guid_key="en_de:cloud",
    )

    card_dict = anki_cards_to_dict({"en_de": [card]})
    restored_cards = anki_cards_from_dict(card_dict)

    assert restored_cards == {"en_de": [card]}


def test_anki_card_to_note() -> None:
    model = create_anki_model()
    card = AnkiCard(
        language_pair="en_de",
        source_language_code="en",
        native_language_code="de",
        lemma="cloud",
        original_word="clouds",
        definition="a visible mass of condensed water vapor",
        gloss="Wolke",
        context_html="Low <b>clouds</b> moved across the ridge.",
        book_title="Broken Orbit",
        book_authors="Evan Shore",
        notes="",
        guid_key="en_de:cloud",
    )

    note = anki_card_to_note(card, model)

    assert note.fields[0] == "cloud"
    assert note.fields[3] == "Wolke"
    assert note.fields[5] == "Broken Orbit - Evan Shore"
    assert note.guid == get_card_guid("en_de:cloud")


def test_get_card_type_native() -> None:
    card = AnkiCard(
        language_pair="de_de",
        source_language_code="de",
        native_language_code="de",
        lemma="Bug",
        original_word="Bug",
        definition="Ein Fehler in einem Computerprogramm.",
        gloss="",
        context_html="Das war ein <b>Bug</b>.",
        book_title="Gewohnheiten im Alltag",
        book_authors="Martin Keller",
        notes="",
        guid_key="de_de:Bug",
    )

    assert get_card_type(card) == NATIVE_NATIVE


def test_get_card_type_reverse() -> None:
    card = AnkiCard(
        language_pair="de_en",
        source_language_code="en",
        native_language_code="de",
        lemma="cloud",
        original_word="clouds",
        definition="a visible mass of condensed water vapor",
        gloss="Wolke",
        context_html="Low {{c1::clouds}} moved across the ridge.",
        book_title="Broken Orbit",
        book_authors="Evan Shore",
        notes="",
        guid_key="de_en:cloud",
    )

    assert get_card_type(card) == NATIVE_FOREIGN


def test_format_book_without_author() -> None:
    card = AnkiCard(
        language_pair="en_de",
        source_language_code="en",
        native_language_code="de",
        lemma="cloud",
        original_word="clouds",
        definition="a visible mass of condensed water vapor",
        gloss="Wolke",
        context_html="Low <b>clouds</b> moved across the ridge.",
        book_title="Broken Orbit",
        book_authors="",
        notes="",
        guid_key="en_de:cloud",
    )

    assert format_book(card) == "Broken Orbit"


def test_write_apkg(tmp_path: Path) -> None:
    card = AnkiCard(
        language_pair="de_de",
        source_language_code="de",
        native_language_code="de",
        lemma="Bug",
        original_word="Bug",
        definition="Ein Fehler in einem Computerprogramm.",
        gloss="",
        context_html="Das war ein <b>Bug</b>.",
        book_title="Gewohnheiten im Alltag",
        book_authors="Martin Keller",
        notes="",
        guid_key="de_de:Bug",
    )
    output_path = tmp_path / "anki_de_de.apkg"

    write_apkg([card], output_path, "Kindle de_de")

    assert output_path.is_file()


def test_write_apkg_empty_cards(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        write_apkg([], tmp_path / "empty.apkg", "Empty")
