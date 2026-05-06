import os
from dotenv import load_dotenv
from google import genai
from google.genai import errors
from google.genai.types import GenerateContentConfigDict, GenerateContentResponse
from pydantic import ValidationError
from typing import cast
from kindle_to_anki.models import BaseVocabularyItem, GeminiAPIError, GeminiHighDemandError, NativeDefinitionBatch, \
    ForeignVocabularyBatch, PromptType, PromptJob

ResponseBatch = NativeDefinitionBatch | ForeignVocabularyBatch
ResponseSchema = type[NativeDefinitionBatch] | type[ForeignVocabularyBatch]
MAX_GEMINI_ATTEMPTS = 3
DEFAULT_GEMINI_MODEL = "gemini-2.5-flash"


def get_environment_value(name: str, default: str | None = None, placeholder: str | None = None) -> str:
    """
    Reads a value from the environment, optionally falling back to a default.
    :param name: Environment variable name
    :param default: Value to return when the environment variable is not set
    :param placeholder: Placeholder value that should be treated as missing
    :return: Environment value or default
    """
    load_dotenv()
    value = os.getenv(name)
    if value and value != placeholder:
        return value
    if default is not None:
        return default
    else:
        raise ValueError(f"{name} is not set in environment variables.")


def get_required_api_key(name: str) -> str:
    """
    Reads a required API key from the environment.
    :param name: Environment variable name
    :return: API key value
    """
    return get_environment_value(name, placeholder="your_api_key_here")


def get_gemini_model() -> str:
    """
    Reads the Gemini model from the environment, falling back to the default model.
    :return: Gemini model identifier
    """
    return get_environment_value("GEMINI_MODEL", DEFAULT_GEMINI_MODEL)

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
        if e.code == 503:
            raise GeminiHighDemandError(e.code, e.message) from e
        raise GeminiAPIError(e.code, e.message) from e

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
    language_pair = f"{job.native_language_code}_{job.source_language_code}"
    for attempt in range(MAX_GEMINI_ATTEMPTS):
        try:
            response = call_gemini_client(client, job, response_schema, model)
            break
        except GeminiHighDemandError:
            if attempt == MAX_GEMINI_ATTEMPTS - 1:
                print(
                    f"Gemini high demand for {language_pair} batch with {len(job.words)} words "
                    f"after {MAX_GEMINI_ATTEMPTS} attempts."
                )
                raise
            print(
                f"Gemini high demand for {language_pair} batch with {len(job.words)} words. "
                f"Retry {attempt + 2}/{MAX_GEMINI_ATTEMPTS}."
            )
    parsed_response = parse_response(response, response_schema)
    validate_response_matches_job(parsed_response, job)
    job.gemini_response = response
    job.parsed_response = parsed_response
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

def response_batches_to_dict(results: dict[str, list[ResponseBatch]]) -> dict[str, list[dict]]:
    """
    Converts response batches to JSON-compatible dictionaries.
    :param results: Dictionary of processed response batches by language pair
    :return: Dictionary with response batches converted to dictionaries
    """
    return {
        language_pair: [batch.model_dump() for batch in batches]
        for language_pair, batches in results.items()
    }
