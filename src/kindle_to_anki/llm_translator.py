import os
from dotenv import load_dotenv
from google import genai
from google.genai import errors
from google.genai.types import GenerateContentConfigDict, GenerateContentResponse
from pydantic import ValidationError
from typing import cast
from kindle_to_anki.models import BaseVocabularyItem, NativeDefinitionBatch, ForeignVocabularyBatch, PromptType, \
    PromptJob

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


