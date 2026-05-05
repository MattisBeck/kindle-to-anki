from dataclasses import dataclass
from enum import Enum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


@dataclass(frozen=True)
class SourceBook:
    title: str
    authors: str


@dataclass(frozen=True)
class WordRecord:
    word: str
    lang: str
    stem: str
    context: str
    origin: SourceBook


class BaseVocabularyItem(BaseModel):  # Shared fields for both card types
    model_config = ConfigDict(extra="forbid")  # No unwanted fields

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
    pass  # No gloss field because a translation would be nonsense


class ForeignVocabularyItem(BaseVocabularyItem):  # result for de/en, en/de etc.
    gloss: str  # short translation of the lemma in the user's native language, if helpful


class NativeDefinitionBatch(BaseModel):  # batch response for native definition cards
    model_config = ConfigDict(extra="forbid")  # no unexpected top-level fields
    items: list[NativeDefinitionItem]  # results without gloss field, focused on definitions in the target language


class ForeignVocabularyBatch(BaseModel):  # batch response for foreign vocabulary cards
    model_config = ConfigDict(extra="forbid")  # no unexpected top-level fields
    items: list[ForeignVocabularyItem]  # results with gloss field


class PromptType(Enum):
    NATIVE_DEFINITION = "native_definition"
    FOREIGN_VOCABULARY = "foreign_vocabulary"


@dataclass
class PromptJob:
    prompt: str
    type: PromptType
    words: list[WordRecord]
    native_language_code: str
    source_language_code: str
    raw_response: str | None = None
    parsed_response: NativeDefinitionBatch | ForeignVocabularyBatch | None = None
