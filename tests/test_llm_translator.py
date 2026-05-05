import pytest

from kindle_to_anki.llm_translator import get_gemini_api_key, get_required_api_key, get_response_schema
from kindle_to_anki.models import ForeignVocabularyBatch, NativeDefinitionBatch, PromptJob, PromptType


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
