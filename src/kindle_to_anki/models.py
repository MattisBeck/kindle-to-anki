"""Shared data models for Kindle records, Gemini responses, and Anki cards."""

from dataclasses import dataclass
from enum import Enum
from typing import Literal

from google.genai.types import GenerateContentResponse
from pydantic import BaseModel, Field


@dataclass(frozen=True)
class SourceBook:
    """Book metadata attached to a Kindle vocabulary lookup."""

    title: str
    authors: str


@dataclass(frozen=True)
class WordRecord:
    """One vocabulary lookup extracted from the Kindle database."""

    word: str
    lang: str
    stem: str
    context: str
    origin: SourceBook


@dataclass(frozen=True)
class AnkiCard:
    """Fully prepared card data ready for genanki note generation."""

    language_pair: str
    source_language_code: str
    native_language_code: str
    lemma: str
    original_word: str
    definition: str
    gloss: str
    context_html: str
    book_title: str
    book_authors: str
    notes: str
    guid_key: str


class BaseVocabularyItem(BaseModel):  # Shared fields for both card types
    """Common Gemini response fields used by all vocabulary card types."""

    item_index: int = Field(ge=0)  # Index in prompt batch
    lemma: str  # Dictionary form of the word
    definition: str  # Context specific definition
    notes: str = ""  # optional notes for the user
    ambiguity: Literal["low", "medium", "high"]  # ambiguity level of the word in context
    sense: str = ""  # specific meaning in context, if identifiable
    domain: str = ""  # semantic domain (e.g. "finance", "biology"), if identifiable
    alternatives: list[str] = Field(default_factory=list, max_length=3)  # short alternatives / synonyms, if helpful
    formality: str = ""  # formality level (e.g. "formal", "colloquial"), if relevant
    false_friend: bool = False  # risk of being a false friend in the given context
    false_friend_note: str = ""  # explanation if it's a false friend
    collocations: list[str] = Field(default_factory=list, max_length=2)  # typical collocations in the given context, if helpful
    anchor: str  # example sentence or phrase from the text that illustrates the usage of the word in context
    confidence: float = Field(ge=0.0, le=1.0)  # model's confidence in the provided definition and other fields


class NativeDefinitionItem(BaseVocabularyItem):  # result for de/de, en/en etc.
    """Gemini response item for a native-language definition card."""

    pass  # No gloss field because a translation would be nonsense


class ForeignVocabularyItem(BaseVocabularyItem):  # result for de/en, en/de etc.
    """Gemini response item for a foreign-language vocabulary card."""

    gloss: str  # short translation of the lemma in the user's native language, if helpful
    cloze_phrase: str = ""  # optional exact context phrase to hide on reverse cards for multiword expressions


class NativeDefinitionBatch(BaseModel):  # batch response for native definition cards
    """Batch response containing native-language definition items."""

    items: list[NativeDefinitionItem]  # results without gloss field, focused on definitions in the target language


class ForeignVocabularyBatch(BaseModel):  # batch response for foreign vocabulary cards
    """Batch response containing foreign-language vocabulary items."""

    items: list[ForeignVocabularyItem]  # results with gloss field


class PromptType(Enum):
    """Supported prompt and response schema variants."""

    NATIVE_DEFINITION = "native_definition"
    FOREIGN_VOCABULARY = "foreign_vocabulary"


@dataclass
class PromptJob:
    """One Gemini prompt together with its source words and parsed response."""

    prompt: str
    type: PromptType
    words: list[WordRecord]
    native_language_code: str
    source_language_code: str
    gemini_response: GenerateContentResponse | None = None
    parsed_response: NativeDefinitionBatch | ForeignVocabularyBatch | None = None


class GeminiAPIError(RuntimeError):
    """Error raised when Gemini returns an API failure response."""

    def __init__(self, code: int, message: str) -> None:
        """Store the Gemini status code and message on the exception."""
        self.code = code
        self.message = message
        super().__init__(f"Gemini API Error: {code}\n{message}")


class GeminiHighDemandError(GeminiAPIError):
    """Error raised when Gemini reports temporary high demand."""

    pass


def normalize_cloze_phrase(cloze_phrase: str, context: str, word: str) -> str:
    """Keep a cloze phrase only when it exactly appears in context and contains the word."""
    normalized = cloze_phrase.strip()
    if normalized and normalized in context and word in normalized:
        return normalized
    return ""
