import os
from dotenv import load_dotenv
from google import genai
from google.genai import errors
from google.genai.types import GenerateContentConfigDict, GenerateContentResponse
from pydantic import BaseModel, Field, ConfigDict, ValidationError
from typing import Literal, cast
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

ResponseBatch = NativeDefinitionBatch | ForeignVocabularyBatch
ResponseSchema = type[NativeDefinitionBatch] | type[ForeignVocabularyBatch]


def get_required_api_key(name: str) -> str:
    load_dotenv()
    api_key = os.getenv(name)
    if not api_key or api_key == "your_api_key_here":
        raise ValueError(f"{name} is not set in environment variables.")
    return api_key

def get_gemini_api_key() -> str:
    return get_required_api_key("GEMINI_API_KEY")

def get_response_schema(prompt_job: PromptJob) -> ResponseSchema:
    if prompt_job.type == PromptType.NATIVE_DEFINITION:
        return NativeDefinitionBatch
    elif prompt_job.type == PromptType.FOREIGN_VOCABULARY:
        return ForeignVocabularyBatch
    else:
        raise ValueError(f"Unsupported prompt type: {prompt_job.type}")


def call_gemini_client(client: genai.Client, job: PromptJob, response_schema:ResponseSchema, model:str) -> GenerateContentResponse:
    """

    :param client:
    :param job:
    :param response_schema:
    :param model:
    :return:
    """
    try:
        response = client.models.generate_content(
            model = model,
            contents = job.prompt,
            config = GenerateContentConfigDict(
                response_mime_type = "application/json",
                response_schema=response_schema.model_json_schema()
            )
        )
    except errors.APIError as e:
        raise RuntimeError(f"Gemini API Error: {e.code}\n{e.message}") from e

    return response

def parse_response(response: GenerateContentResponse, response_schema: ResponseSchema) -> ResponseBatch:
    """
    validates if the response is matching the required schema
    :param response: response object from Gemini
    :param response_schema: The response schema, either a NativeDefinitionBatch or ForeignVocabularyBatch
    :return: The NativeDefinitionBatch or ForeignVocabularyBatch
    """
    response_text = response.text
    if response_text is None:
        raise ValueError(f"Gemini returned no text to parse")
    try:
        return response_schema.model_validate_json(response_text)
    except ValidationError as e:
        ## TODO: Format a new prompt with wrong words
        raise ValueError(f"Gemini returned invalid json: {response.text}") from e

def validate_response_matches_job(response: ResponseBatch, job: PromptJob) -> bool:
    """
    Validates that the response contains the expected number of items matching the job.
    :param response: The parsed response object (NativeDefinitionBatch or ForeignVocabularyBatch)
    :param job: The original PromptJob
    :return: True if response matches job expectations
    :raises ValueError: If response item count or indices don't match the job expectations
    """
    items = cast(list[BaseVocabularyItem], response.items)
    expected_count = len(job.words)
    actual_count = len(items)

    # Check if the number of items matches
    if actual_count != expected_count:
        raise ValueError(
            f"Response item count mismatch: expected {expected_count} items, got {actual_count}. "
            f"Response item indices: {[item.item_index for item in items]}"
        )

    # Check if item indices are correct and in order
    for i, item in enumerate(items):
        if item.item_index != i:
            raise ValueError(
                f"Item index mismatch at position {i}: expected index {i}, got index {item.item_index}. "
                f"All item indices in response: {[item.item_index for item in items]}"
            )

    return True

def process_prompt_job(client: genai.Client, job: PromptJob, model:str) -> ResponseBatch:
    """
    :param client: Gemini API client
    :param job: The prompt job to process
    :param model: The model identifier to use
    :return: The validated response batch
    """
    response_schema = get_response_schema(job)
    response = call_gemini_client(client, job, response_schema, model)
    parsed_response = parse_response(response, response_schema)
    validate_response_matches_job(parsed_response, job)
    return parsed_response

def process_prompt_jobs(prompts: dict[str, list[PromptJob]], api_key: str, model: str) -> dict[str, list[ResponseBatch]]:
    """

    :param prompts: Dictionary of prompt jobs, from get_all_prompts
    :param api_key: Gemini API key
    :param model: Gemini model (e.g. "gemini-3-flash-preview")
    :return: A dictionary mapping each language pair to a list of validated batch responses
    """
    results: dict[str, list[ResponseBatch]] = {}

    with genai.Client(api_key=api_key) as client:
        for prompt_group in prompts.values():
            for job in prompt_group:
                language_pair = f"{job.native_language_code}_{job.source_language_code}"
                processed_response = process_prompt_job(client, job, model)
                results.setdefault(language_pair, []).append(processed_response)

    return results


