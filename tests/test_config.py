from pathlib import Path

import pytest

from kindle_to_anki.config import (
    API_KEY_PLACEHOLDER,
    DEFAULT_ANKI_CARDS_PATH,
    DEFAULT_APKG_DIR,
    DEFAULT_CACHE_PATH,
    DEFAULT_JSON_DIR,
    DEFAULT_RAW_RESPONSE_PATH,
    BATCH_SIZE,
    GEMINI_API_KEY,
    GEMINI_MODEL,
    NATIVE_LANGUAGE_CODE,
    GeminiModel,
    ensure_env_file,
    get_missing_required_config,
    load_app_config,
    normalize_model_name,
    read_env_values,
    set_api_key,
    set_batch_size,
    set_gemini_model,
    set_native_language,
    set_env_values,
    validate_batch_size,
    validate_language_code,
)
from kindle_to_anki.llm_translator import DEFAULT_GEMINI_MODEL


def test_ensure_env_file_copies_example(tmp_path: Path) -> None:
    env_path = tmp_path / ".env"
    example_path = tmp_path / ".env.example"
    example_path.write_text(f'{GEMINI_API_KEY}="{API_KEY_PLACEHOLDER}"\n', encoding="utf-8")

    ensure_env_file(env_path, example_path)

    assert read_env_values(env_path)[GEMINI_API_KEY] == API_KEY_PLACEHOLDER


def test_set_env_values_replaces_and_appends(tmp_path: Path) -> None:
    env_path = tmp_path / ".env"
    env_path.write_text(
        "\n".join(
            [
                "UNKNOWN=value",
                f'{GEMINI_API_KEY}="{API_KEY_PLACEHOLDER}"',
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    set_env_values(
        {
            GEMINI_API_KEY: "secret",
            GEMINI_MODEL: "models/gemini-test",
        },
        env_path,
    )

    values = read_env_values(env_path)
    assert values["UNKNOWN"] == "value"
    assert values[GEMINI_API_KEY] == "secret"
    assert values[GEMINI_MODEL] == "models/gemini-test"


def test_config_setters_validate_and_write(tmp_path: Path) -> None:
    env_path = tmp_path / ".env"

    set_api_key("secret", env_path)
    set_gemini_model("models/gemini-test", env_path)
    set_native_language("DE", env_path)
    set_batch_size("10", env_path)

    config = load_app_config(env_path)
    assert config.api_key == "secret"
    assert config.model == "models/gemini-test"
    assert config.native_language_code == "de"
    assert config.batch_size == 10


def test_load_app_config_defaults_and_missing_required(tmp_path: Path) -> None:
    env_path = tmp_path / ".env"
    env_path.write_text(f'{GEMINI_API_KEY}="{API_KEY_PLACEHOLDER}"\n', encoding="utf-8")

    config = load_app_config(env_path)

    assert config.api_key is None
    assert config.model == DEFAULT_GEMINI_MODEL
    assert config.native_language_code is None
    assert config.batch_size == 10
    assert get_missing_required_config(config) == [GEMINI_API_KEY, NATIVE_LANGUAGE_CODE]


def test_default_output_paths_are_grouped_under_data_subdirectories() -> None:
    assert DEFAULT_APKG_DIR.name == "apkg"
    assert DEFAULT_JSON_DIR.name == "json"
    assert DEFAULT_CACHE_PATH.parent == DEFAULT_JSON_DIR
    assert DEFAULT_RAW_RESPONSE_PATH.parent == DEFAULT_JSON_DIR
    assert DEFAULT_ANKI_CARDS_PATH.parent == DEFAULT_JSON_DIR


def test_validate_language_code() -> None:
    assert validate_language_code("DE") == "de"
    with pytest.raises(ValueError):
        validate_language_code("xx")


def test_validate_batch_size() -> None:
    assert validate_batch_size("2") == 2
    with pytest.raises(ValueError):
        validate_batch_size("0")
    with pytest.raises(ValueError):
        validate_batch_size("abc")


def test_normalize_model_name() -> None:
    models = [GeminiModel("models/gemini-2.5-flash"), GeminiModel("models/other")]

    assert normalize_model_name("gemini-2.5-flash", models) == "models/gemini-2.5-flash"
    assert normalize_model_name("models/other", models) == "models/other"
    assert normalize_model_name("missing", models) is None
