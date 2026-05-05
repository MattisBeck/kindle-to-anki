import pytest
from pytest_mock import MockerFixture

from kindle_to_anki.llm_translator import (
    call_gemini_client,
    get_gemini_api_key,
    get_required_api_key,
    get_response_schema,
    parse_response,
    process_prompt_job,
    process_prompt_jobs,
    response_batches_to_dict,
    validate_response_matches_job,
)
from kindle_to_anki.models import (
    ForeignVocabularyBatch,
    NativeDefinitionBatch,
    PromptJob,
    PromptType,
    SourceBook,
    WordRecord,
)


class FakeResponse:
    def __init__(self, text: str | None) -> None:
        self.text = text


def get_word(word: str = "Haus") -> WordRecord:
    return WordRecord(word, "de", word, "Das Haus ist alt.", SourceBook("Book", "Author"))


def get_native_json(item_index: int = 0) -> str:
    return """
    {
        "items": [
            {
                "item_index": %s,
                "lemma": "Haus",
                "definition": "Gebaeude zum Wohnen",
                "ambiguity": "low",
                "anchor": "Das Haus ist alt.",
                "confidence": 0.9
            }
        ]
    }
    """ % item_index


def get_foreign_json() -> str:
    return """
    {
        "items": [
            {
                "item_index": 0,
                "lemma": "house",
                "definition": "building to live in",
                "ambiguity": "low",
                "anchor": "The house is old.",
                "confidence": 0.9,
                "gloss": "Haus"
            }
        ]
    }
    """


def test_get_required_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TEST_API_KEY", "secret")
    assert get_required_api_key("TEST_API_KEY") == "secret"

def test_get_required_api_key_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("TEST_API_KEY", raising=False)

    with pytest.raises(ValueError):
        get_required_api_key("TEST_API_KEY")

def test_get_required_api_key_placeholder(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TEST_API_KEY", "your_api_key_here")

    with pytest.raises(ValueError):
        get_required_api_key("TEST_API_KEY")

def test_get_gemini_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GEMINI_API_KEY", "gemini-secret")
    assert get_gemini_api_key() == "gemini-secret"

def test_get_response_schema_native_definition() -> None:
    prompt_job = PromptJob("", PromptType.NATIVE_DEFINITION, [], "de", "de")
    assert get_response_schema(prompt_job) == NativeDefinitionBatch

def test_get_response_schema_foreign_vocabulary() -> None:
    prompt_job = PromptJob("", PromptType.FOREIGN_VOCABULARY, [], "de", "en")
    assert get_response_schema(prompt_job) == ForeignVocabularyBatch

def test_call_gemini_client(mocker: MockerFixture) -> None:
    client = mocker.Mock()
    response = FakeResponse("{}")
    client.models.generate_content.return_value = response
    prompt_job = PromptJob("prompt text", PromptType.NATIVE_DEFINITION, [], "de", "de")

    result = call_gemini_client(client, prompt_job, NativeDefinitionBatch, "gemini-test")

    assert result == response
    client.models.generate_content.assert_called_once()
    arguments = client.models.generate_content.call_args.kwargs
    assert arguments["model"] == "gemini-test"
    assert arguments["contents"] == "prompt text"
    assert arguments["config"]["response_mime_type"] == "application/json"

def test_call_gemini_client_api_error(mocker: MockerFixture) -> None:
    class FakeAPIError(Exception):
        code = 500
        message = "broken"

    client = mocker.Mock()
    client.models.generate_content.side_effect = FakeAPIError()
    prompt_job = PromptJob("prompt text", PromptType.NATIVE_DEFINITION, [], "de", "de")
    mocker.patch("kindle_to_anki.llm_translator.errors.APIError", FakeAPIError)

    with pytest.raises(RuntimeError):
        call_gemini_client(client, prompt_job, NativeDefinitionBatch, "gemini-test")

def test_parse_response_native_definition() -> None:
    response = FakeResponse(get_native_json())
    parsed_response = parse_response(response, NativeDefinitionBatch)

    assert isinstance(parsed_response, NativeDefinitionBatch)
    assert parsed_response.items[0].lemma == "Haus"

def test_parse_response_foreign_vocabulary() -> None:
    response = FakeResponse(get_foreign_json())
    parsed_response = parse_response(response, ForeignVocabularyBatch)

    assert isinstance(parsed_response, ForeignVocabularyBatch)
    assert parsed_response.items[0].gloss == "Haus"

def test_parse_response_empty_text() -> None:
    response = FakeResponse(None)

    with pytest.raises(ValueError):
        parse_response(response, NativeDefinitionBatch)

def test_parse_response_invalid_json() -> None:
    response = FakeResponse("{}")

    with pytest.raises(ValueError):
        parse_response(response, NativeDefinitionBatch)

def test_validate_response_matches_job() -> None:
    response = NativeDefinitionBatch.model_validate_json(get_native_json())
    prompt_job = PromptJob("", PromptType.NATIVE_DEFINITION, [get_word()], "de", "de")

    assert validate_response_matches_job(response, prompt_job)

def test_validate_response_matches_job_wrong_count() -> None:
    response = NativeDefinitionBatch.model_validate_json(get_native_json())
    prompt_job = PromptJob("", PromptType.NATIVE_DEFINITION, [get_word(), get_word("Baum")], "de", "de")

    with pytest.raises(ValueError):
        validate_response_matches_job(response, prompt_job)

def test_validate_response_matches_job_wrong_index() -> None:
    response = NativeDefinitionBatch.model_validate_json(get_native_json(1))
    prompt_job = PromptJob("", PromptType.NATIVE_DEFINITION, [get_word()], "de", "de")

    with pytest.raises(ValueError):
        validate_response_matches_job(response, prompt_job)

def test_process_prompt_job(mocker: MockerFixture) -> None:
    client = mocker.Mock()
    response = FakeResponse(get_native_json())
    parsed_response = NativeDefinitionBatch.model_validate_json(get_native_json())
    prompt_job = PromptJob("", PromptType.NATIVE_DEFINITION, [get_word()], "de", "de")

    mocker.patch("kindle_to_anki.llm_translator.call_gemini_client", return_value=response)
    mocker.patch("kindle_to_anki.llm_translator.parse_response", return_value=parsed_response)
    validate_mock = mocker.patch("kindle_to_anki.llm_translator.validate_response_matches_job", return_value=True)

    assert process_prompt_job(client, prompt_job, "gemini-test") == parsed_response
    validate_mock.assert_called_once_with(parsed_response, prompt_job)

def test_process_prompt_jobs(mocker: MockerFixture) -> None:
    client = mocker.Mock()
    client_context = mocker.Mock()
    client_context.__enter__ = mocker.Mock(return_value=client)
    client_context.__exit__ = mocker.Mock(return_value=None)
    mocker.patch("kindle_to_anki.llm_translator.genai.Client", return_value=client_context)

    native_response = NativeDefinitionBatch.model_validate_json(get_native_json())
    foreign_response = ForeignVocabularyBatch.model_validate_json(get_foreign_json())
    process_mock = mocker.patch(
        "kindle_to_anki.llm_translator.process_prompt_job",
        side_effect=[native_response, foreign_response]
    )
    native_job = PromptJob("", PromptType.NATIVE_DEFINITION, [get_word()], "de", "de")
    foreign_job = PromptJob("", PromptType.FOREIGN_VOCABULARY, [get_word("house")], "de", "en")

    results = process_prompt_jobs({"de": [native_job], "en": [foreign_job]}, "api-key", "gemini-test")

    assert results == {"de_de": [native_response], "de_en": [foreign_response]}
    assert process_mock.call_count == 2

def test_response_batches_to_dict() -> None:
    response = NativeDefinitionBatch.model_validate_json(get_native_json())

    results = response_batches_to_dict({"de_de": [response]})

    assert results["de_de"][0]["items"][0]["lemma"] == "Haus"
