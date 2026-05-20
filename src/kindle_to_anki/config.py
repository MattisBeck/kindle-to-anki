"""Load, validate, and persist application configuration."""

import os
import re
import shutil
from dataclasses import dataclass
from pathlib import Path

from dotenv import dotenv_values
from google import genai

from kindle_to_anki.llm_translator import DEFAULT_GEMINI_MODEL
from kindle_to_anki.prompt_building import languages


# Default paths for normal CLI runs
WORKING_DIRECTORY = Path.cwd()
ENV_PATH = WORKING_DIRECTORY / ".env"
ENV_EXAMPLE_PATH = WORKING_DIRECTORY / ".env.example"
DEFAULT_DB_PATH = WORKING_DIRECTORY / "put_vocab_db_here" / "vocab.db"
DEFAULT_DATA_DIR = WORKING_DIRECTORY / "data"
DEFAULT_APKG_DIR = DEFAULT_DATA_DIR / "apkg"
DEFAULT_JSON_DIR = DEFAULT_DATA_DIR / "json"
DEFAULT_CACHE_PATH = DEFAULT_JSON_DIR / "cache.json"
DEFAULT_RAW_RESPONSE_PATH = DEFAULT_JSON_DIR / "raw_response.json"
DEFAULT_ANKI_CARDS_PATH = DEFAULT_JSON_DIR / "anki_cards.json"
DEFAULT_NATIVE_LANGUAGE_CODE = "de"
DEFAULT_BATCH_SIZE = 10
API_KEY_PLACEHOLDER = "your_api_key_here"

GEMINI_API_KEY = "GEMINI_API_KEY"
GEMINI_MODEL = "GEMINI_MODEL"
NATIVE_LANGUAGE_CODE = "NATIVE_LANGUAGE_CODE"
BATCH_SIZE = "BATCH_SIZE"


@dataclass(frozen=True)
class AppConfig:
    """Resolved application configuration used by CLI and pipeline code."""

    api_key: str | None
    model: str
    native_language_code: str | None
    batch_size: int
    env_path: Path


@dataclass(frozen=True)
class GeminiModel:
    """Gemini model metadata returned by the model listing endpoint."""

    name: str
    display_name: str | None = None


def ensure_env_file(env_path: Path = ENV_PATH, example_path: Path = ENV_EXAMPLE_PATH) -> None:
    """Create a .env file from the example template or defaults when missing."""
    if env_path.exists():
        return
    # Start new installs from the checked-in template when it exists
    env_path.parent.mkdir(parents=True, exist_ok=True)
    if example_path.exists():
        shutil.copyfile(example_path, env_path)
        return
    env_path.write_text(
        "\n".join(
            [
                f'{GEMINI_API_KEY}="{API_KEY_PLACEHOLDER}"',
                f'{GEMINI_MODEL}="{DEFAULT_GEMINI_MODEL}"',
                f'{NATIVE_LANGUAGE_CODE}="{DEFAULT_NATIVE_LANGUAGE_CODE}"',
                f'{BATCH_SIZE}="{DEFAULT_BATCH_SIZE}"',
                "",
            ]
        ),
        encoding="utf-8",
    )


def read_env_values(env_path: Path = ENV_PATH) -> dict[str, str]:
    """Read key-value pairs from a dotenv file."""
    if not env_path.exists():
        return {}
    values = dotenv_values(env_path)
    return {key: value for key, value in values.items() if value is not None}


def get_config_value(name: str, env_path: Path = ENV_PATH) -> str | None:
    """Read a config value, preferring the real environment over .env."""
    # Real environment variables override .env values
    if os.getenv(name) is not None:
        return os.getenv(name)
    return read_env_values(env_path).get(name)


def is_missing_api_key(api_key: str | None) -> bool:
    """Return whether an API key is absent or still set to the placeholder."""
    return api_key is None or api_key.strip() in {"", API_KEY_PLACEHOLDER}


def validate_language_code(language_code: str) -> str:
    """Normalize and validate a supported language code."""
    normalized = language_code.strip().lower()
    if normalized not in languages:
        raise ValueError(f"Unsupported language code: {language_code}")
    return normalized


def validate_batch_size(batch_size: str | int) -> int:
    """Parse and validate a positive batch size."""
    try:
        parsed = int(batch_size)
    except (TypeError, ValueError) as e:
        raise ValueError(f"Batch size must be a positive integer: {batch_size}") from e
    if parsed < 1:
        raise ValueError(f"Batch size must be a positive integer: {batch_size}")
    return parsed


def load_app_config(env_path: Path = ENV_PATH) -> AppConfig:
    """Load normalized application configuration from environment and dotenv values."""
    # Keep normalization at the boundary so CLI and future GUI code can share this config object
    api_key = get_config_value(GEMINI_API_KEY, env_path)
    model = get_config_value(GEMINI_MODEL, env_path) or DEFAULT_GEMINI_MODEL
    native_language_code = get_config_value(NATIVE_LANGUAGE_CODE, env_path)
    batch_size = get_config_value(BATCH_SIZE, env_path) or str(DEFAULT_BATCH_SIZE)
    return AppConfig(
        api_key=None if is_missing_api_key(api_key) else api_key,
        model=model.strip(),
        native_language_code=(
            validate_language_code(native_language_code)
            if native_language_code and native_language_code.strip()
            else None
        ),
        batch_size=validate_batch_size(batch_size),
        env_path=env_path,
    )


def get_missing_required_config(config: AppConfig) -> list[str]:
    """Return the required configuration keys that are missing."""
    missing = []
    if is_missing_api_key(config.api_key):
        missing.append(GEMINI_API_KEY)
    if config.native_language_code is None:
        missing.append(NATIVE_LANGUAGE_CODE)
    return missing


def quote_env_value(value: str | int) -> str:
    """Quote and escape a value for writing to a dotenv file."""
    escaped = str(value).replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def set_env_value(name: str, value: str | int, env_path: Path = ENV_PATH) -> None:
    """Persist one dotenv value."""
    set_env_values({name: str(value)}, env_path)


def set_env_values(values: dict[str, str], env_path: Path = ENV_PATH) -> None:
    """Persist multiple dotenv values while preserving unrelated lines."""
    ensure_env_file(env_path)
    lines = env_path.read_text(encoding="utf-8").splitlines()
    remaining = dict(values)
    updated_lines = []

    # Preserve unknown lines and only replace keys we own
    for line in lines:
        replaced = False
        for name, value in list(remaining.items()):
            if re.match(rf"^\s*{re.escape(name)}\s*=", line):
                updated_lines.append(f"{name}={quote_env_value(value)}")
                del remaining[name]
                replaced = True
                break
        if not replaced:
            updated_lines.append(line)

    for name, value in remaining.items():
        updated_lines.append(f"{name}={quote_env_value(value)}")

    env_path.write_text("\n".join(updated_lines) + "\n", encoding="utf-8")


def set_api_key(api_key: str, env_path: Path = ENV_PATH) -> None:
    """Validate and persist the Gemini API key."""
    if not api_key.strip():
        raise ValueError("API key must not be empty")
    set_env_value(GEMINI_API_KEY, api_key.strip(), env_path)


def set_gemini_model(model: str, env_path: Path = ENV_PATH) -> None:
    """Validate and persist the Gemini model name."""
    if not model.strip():
        raise ValueError("Gemini model must not be empty")
    set_env_value(GEMINI_MODEL, model.strip(), env_path)


def set_native_language(language_code: str, env_path: Path = ENV_PATH) -> None:
    """Validate and persist the native language code."""
    set_env_value(NATIVE_LANGUAGE_CODE, validate_language_code(language_code), env_path)


def set_batch_size(batch_size: str | int, env_path: Path = ENV_PATH) -> None:
    """Validate and persist the Gemini batch size."""
    set_env_value(BATCH_SIZE, str(validate_batch_size(batch_size)), env_path)


def get_generate_content_models(api_key: str) -> list[GeminiModel]:
    """List Gemini models that support generateContent for the API key."""
    # A successful models.list call also validates the API key
    with genai.Client(api_key=api_key) as client:
        models = list(client.models.list())

    generate_content_models = []
    for model in models:
        supported_actions = getattr(model, "supported_actions", None) or []
        if "generateContent" not in supported_actions:
            continue
        name = getattr(model, "name", "")
        if not name:
            continue
        display_name = getattr(model, "display_name", None)
        generate_content_models.append(GeminiModel(name=name, display_name=display_name))

    return sorted(generate_content_models, key=lambda model: (model.display_name or model.name).lower())


def normalize_model_name(model_name: str, models: list[GeminiModel]) -> str | None:
    """Resolve user input to an exact Gemini model name when available."""
    requested = model_name.strip()
    for model in models:
        if requested == model.name:
            return model.name
        # Let users type gemini-... even when the API returns models/gemini-...
        if model.name.startswith("models/") and requested == model.name.removeprefix("models/"):
            return model.name
    return None
