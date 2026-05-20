"""Command-line interface for configuring and running kindle-to-anki."""

import argparse
import sys
from getpass import getpass
from pathlib import Path

from kindle_to_anki.config import (
    API_KEY_PLACEHOLDER,
    BATCH_SIZE,
    DEFAULT_BATCH_SIZE,
    DEFAULT_DB_PATH,
    DEFAULT_NATIVE_LANGUAGE_CODE,
    ENV_EXAMPLE_PATH,
    ENV_PATH,
    GEMINI_API_KEY,
    GEMINI_MODEL,
    NATIVE_LANGUAGE_CODE,
    AppConfig,
    GeminiModel,
    ensure_env_file,
    get_generate_content_models,
    get_missing_required_config,
    is_missing_api_key,
    load_app_config,
    normalize_model_name,
    set_api_key,
    set_batch_size,
    set_gemini_model,
    set_native_language,
    validate_batch_size,
    validate_language_code,
)
from kindle_to_anki.llm_translator import DEFAULT_GEMINI_MODEL
from kindle_to_anki.models import GeminiAPIError, GeminiHighDemandError
from kindle_to_anki.pipeline import run_pipeline


def build_parser() -> argparse.ArgumentParser:
    """Build the top-level command-line argument parser."""
    parser = argparse.ArgumentParser(
        prog="kindle-to-anki",
        description="Create Anki decks from a Kindle vocab.db file.",
    )
    parser.add_argument("--config", action="store_true", help="run interactive configuration")
    parser.add_argument("--status", action="store_true", help="show configuration and Gemini API status")
    parser.add_argument("--db-path", type=Path, default=DEFAULT_DB_PATH, help="path to Kindle vocab.db")
    parser.add_argument("--set-api-key", help="set and validate GEMINI_API_KEY")
    parser.add_argument("--set-gemini-model", help="set GEMINI_MODEL after validating it supports generateContent")
    parser.add_argument("--set-native-language", help="persist NATIVE_LANGUAGE_CODE, e.g. de or en")
    parser.add_argument("--set-batch-size", help="persist BATCH_SIZE")
    parser.add_argument("--native-language", help="override native language for this run only")
    parser.add_argument("--batch-size", help="override batch size for this run only")
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="show progress while reading, calling Gemini, and writing files",
    )
    return parser


def format_model(model: GeminiModel) -> str:
    """Format a Gemini model for terminal output."""
    if model.display_name and model.display_name != model.name:
        return f"{model.name} ({model.display_name})"
    return model.name


def print_models(models: list[GeminiModel]) -> None:
    """Print available Gemini models for interactive selection."""
    if not models:
        print("No generateContent models found.")
        return
    print("Available generateContent models:")
    for index, model in enumerate(models, start=1):
        print(f"  {index}. {format_model(model)}")


def fetch_generate_content_models(api_key: str) -> list[GeminiModel]:
    """Fetch generateContent models and convert provider errors for CLI display."""
    try:
        return get_generate_content_models(api_key)
    except Exception as e:
        # Hide provider-specific exceptions behind one CLI-friendly error
        raise ValueError(f"Gemini API key is invalid or the API is unreachable: {e}") from e


def choose_model(
    models: list[GeminiModel],
    current_model: str,
    input_func=input,
) -> str:
    """Prompt the user to choose a Gemini model from the available models."""
    if not models:
        raise ValueError("No generateContent models are available for this API key")

    current_normalized = normalize_model_name(current_model, models)
    default_normalized = normalize_model_name(DEFAULT_GEMINI_MODEL, models)
    # Prefer the saved model, then the app default, then the first API result
    suggested_model = current_normalized or default_normalized or models[0].name

    print_models(models)
    prompt = f"Gemini model [{suggested_model}]: "
    selected = input_func(prompt).strip()
    if not selected:
        return suggested_model
    if selected.isdigit():
        index = int(selected) - 1
        if index < 0 or index >= len(models):
            raise ValueError(f"Model selection out of range: {selected}")
        return models[index].name
    normalized = normalize_model_name(selected, models)
    if normalized is None:
        raise ValueError(f"Model does not support generateContent or was not found: {selected}")
    return normalized


def configure_interactively(
    env_path: Path = ENV_PATH,
    example_path: Path = ENV_EXAMPLE_PATH,
    input_func=input,
    secret_input_func=getpass,
) -> AppConfig:
    """Run the interactive first-time configuration flow."""
    ensure_env_file(env_path, example_path)
    current_config = load_app_config(env_path)

    current_language = current_config.native_language_code or DEFAULT_NATIVE_LANGUAGE_CODE
    native_language = input_func(f"Native language code [{current_language}]: ").strip() or current_language
    native_language = validate_language_code(native_language)

    current_batch_size = current_config.batch_size or DEFAULT_BATCH_SIZE
    batch_size_input = input_func(f"Batch size [{current_batch_size}]: ").strip()
    batch_size = validate_batch_size(batch_size_input or current_batch_size)

    if current_config.api_key:
        api_key = secret_input_func("Gemini API key [keep current]: ").strip() or current_config.api_key
    else:
        api_key = secret_input_func("Gemini API key: ").strip()
    if is_missing_api_key(api_key):
        raise ValueError(f"{GEMINI_API_KEY} is required")

    # Validate the key before writing it to .env
    models = fetch_generate_content_models(api_key)
    model = choose_model(models, current_config.model, input_func)

    set_api_key(api_key, env_path)
    set_native_language(native_language, env_path)
    set_batch_size(batch_size, env_path)
    set_gemini_model(model, env_path)
    print(f"Configuration written to {env_path}")
    return load_app_config(env_path)


def print_status(env_path: Path = ENV_PATH) -> int:
    """Print current configuration and Gemini API status."""
    ensure_env_file(env_path)
    config = load_app_config(env_path)
    print(f".env: {env_path}")
    print(f"Default DB: {DEFAULT_DB_PATH}")
    print(f"{GEMINI_MODEL}: {config.model}")
    print(f"{NATIVE_LANGUAGE_CODE}: {config.native_language_code or 'not set'}")
    print(f"{BATCH_SIZE}: {config.batch_size}")

    if is_missing_api_key(config.api_key):
        print(f"{GEMINI_API_KEY}: not set")
        print(f"Run `uv run kindle-to-anki --config` to configure the project.")
        return 1

    print(f"{GEMINI_API_KEY}: set")
    models = fetch_generate_content_models(config.api_key or API_KEY_PLACEHOLDER)
    print("Gemini API key: valid")
    print_models(models)
    return 0


def apply_setters(args: argparse.Namespace, env_path: Path = ENV_PATH) -> int:
    """Apply non-interactive configuration setter arguments."""
    ensure_env_file(env_path)
    models: list[GeminiModel] | None = None

    if args.set_api_key:
        # Only persist the key after Gemini accepts it
        models = fetch_generate_content_models(args.set_api_key)
        set_api_key(args.set_api_key, env_path)
        print(f"{GEMINI_API_KEY} written to {env_path}")
        print_models(models)

    if args.set_native_language:
        set_native_language(args.set_native_language, env_path)
        print(f"{NATIVE_LANGUAGE_CODE} written to {env_path}")

    if args.set_batch_size:
        set_batch_size(args.set_batch_size, env_path)
        print(f"{BATCH_SIZE} written to {env_path}")

    if args.set_gemini_model:
        config = load_app_config(env_path)
        if is_missing_api_key(config.api_key):
            raise ValueError(f"{GEMINI_API_KEY} must be set before choosing a Gemini model")
        if models is None:
            models = fetch_generate_content_models(config.api_key or "")
        normalized = normalize_model_name(args.set_gemini_model, models)
        if normalized is None:
            print_models(models)
            raise ValueError(f"Model does not support generateContent or was not found: {args.set_gemini_model}")
        set_gemini_model(normalized, env_path)
        print(f"{GEMINI_MODEL} written to {env_path}")

    return 0


def has_setter(args: argparse.Namespace) -> bool:
    """Return whether any configuration setter argument was provided."""
    return any(
        [
            args.set_api_key,
            args.set_gemini_model,
            args.set_native_language,
            args.set_batch_size,
        ]
    )


def run_pipeline_command(args: argparse.Namespace, env_path: Path = ENV_PATH) -> int:
    """Validate CLI inputs and run the reusable pipeline."""
    # Keep this command as a thin adapter around reusable config and pipeline code
    ensure_env_file(env_path)
    config = load_app_config(env_path)
    missing = get_missing_required_config(config)
    if missing:
        # First run should guide the user instead of failing with a config error
        print(f"Missing configuration: {', '.join(missing)}")
        print("Starting interactive configuration.")
        config = configure_interactively(env_path)

    native_language = (
        validate_language_code(args.native_language)
        if args.native_language
        else config.native_language_code
    )
    if native_language is None:
        raise ValueError(f"{NATIVE_LANGUAGE_CODE} is required")

    batch_size = validate_batch_size(args.batch_size) if args.batch_size else config.batch_size
    if is_missing_api_key(config.api_key):
        raise ValueError(f"{GEMINI_API_KEY} is required. Run `uv run kindle-to-anki --config`.")

    progress_callback = print_progress if args.verbose else None
    result = run_pipeline(
        db_path=args.db_path,
        api_key=config.api_key or "",
        model=config.model,
        native_language_code=native_language,
        batch_size=batch_size,
        progress_callback=progress_callback,
    )
    print(f"Processed {result.words_read} words.")
    if result.apkg_paths:
        print("Created APKG files:")
        for path in result.apkg_paths:
            print(f"  - {path}")
    else:
        print("No new words to process.")
    return 0


def print_progress(message: str) -> None:
    """Print a progress message to stderr immediately."""
    print(message, file=sys.stderr, flush=True)


def main(argv: list[str] | None = None, env_path: Path = ENV_PATH) -> int:
    """Run the CLI and return a process exit code."""
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        # Route each mode here; the implementation work stays in smaller helpers
        if args.config:
            configure_interactively(env_path)
            return 0
        if args.status:
            return print_status(env_path)
        if has_setter(args):
            return apply_setters(args, env_path)
        return run_pipeline_command(args, env_path)
    except (EOFError, KeyboardInterrupt):
        print("\nConfiguration cancelled.", file=sys.stderr)
        return 1
    except GeminiHighDemandError as e:
        print("Gemini is currently overloaded after all retry attempts.", file=sys.stderr)
        print(e.message, file=sys.stderr)
        print("Try again later, lower --batch-size, or choose another model with --set-gemini-model.", file=sys.stderr)
        return 1
    except GeminiAPIError as e:
        print(f"Gemini API error {e.code}: {e.message}", file=sys.stderr)
        return 1
    except (FileNotFoundError, ValueError) as e:
        print(e, file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
