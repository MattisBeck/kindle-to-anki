import os
from dotenv import load_dotenv
from google import genai
from google.genai import errors
from google.genai.types import GenerateContentConfigDict, GenerateContentResponse
from pydantic import BaseModel, Field, ConfigDict, ValidationError
from typing import Literal
from kindle_to_anki.prompt_building import PromptJob, PromptType

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
    register: str = ""  # formality level (e.g. "formal", "colloquial"), if relevant
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



def get_required_api_key(name: str) -> str:
    load_dotenv()
    api_key = os.getenv(name)
    if not api_key or api_key == "your_api_key_here":
        raise ValueError(f"{name} is not set in environment variables.")
    return api_key

def get_gemini_api_key() -> str:
    return get_required_api_key("GEMINI_API_KEY")

def get_response_schema(prompt_job: PromptJob) -> type[NativeDefinitionBatch | ForeignVocabularyBatch]:
    if prompt_job.type == PromptType.NATIVE_DEFINITION:
        return NativeDefinitionBatch
    elif prompt_job.type == PromptType.FOREIGN_VOCABULARY:
        return ForeignVocabularyBatch
    else:
        raise ValueError(f"Unsupported prompt type: {prompt_job.type}")


def call_gemini_client(client: genai.Client, job: PromptJob, response_schema:type[NativeDefinitionBatch | ForeignVocabularyBatch], model:str) -> GenerateContentResponse:
    try:
        response = client.models.generate_content(
            model = model,
            contents = job.prompt,
            config = GenerateContentConfigDict(
                response_mime_type = "application/json",
                response_schema=response_schema
            )
        )
    except errors.APIError as e:
        raise RuntimeError(f"Gemini API Error: {e.code}\n{e.message}") from e

    return response

def parse_response(response: GenerateContentResponse, response_schema: type[NativeDefinitionBatch | ForeignVocabularyBatch]) -> NativeDefinitionBatch | ForeignVocabularyBatch:
    if response.text is None:
        raise ValueError(f"Gemini returned no text to parse")
    try:
        return response_schema.model_validate_json(response.text)
    except ValidationError:
        ## TODO: Format a new prompt with wrong words
        raise ValueError(f"Gemini returned invalid json: {response.text}")