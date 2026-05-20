"""Reusable workflow for turning Kindle vocabulary into Anki output files."""

import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from kindle_to_anki.anki_converter import anki_cards_to_dict, prompt_jobs_to_anki_cards, write_apkg
from kindle_to_anki.config import (
    DEFAULT_ANKI_CARDS_PATH,
    DEFAULT_APKG_DIR,
    DEFAULT_CACHE_PATH,
    DEFAULT_RAW_RESPONSE_PATH,
)
from kindle_to_anki.db_reader import add_words_to_cache, extract_information
from kindle_to_anki.llm_translator import process_prompt_jobs, response_batches_to_dict
from kindle_to_anki.prompt_building import get_all_prompts, separate_words_by_language


ProgressCallback = Callable[[str], None]
ANKI_PARENT_DECK = "Kindle"


@dataclass(frozen=True)
class PipelineResult:
    """Output summary for one pipeline run."""

    words_read: int
    apkg_paths: list[Path]
    raw_response_path: Path
    anki_cards_path: Path


def read_json_object(path: Path) -> dict[str, list[dict[str, Any]]]:
    """Read a grouped JSON object from disk, returning an empty object when absent."""
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as file:
        data = json.load(file)
    if not isinstance(data, dict):
        raise ValueError(f"Expected JSON object in {path}")
    return data


def write_json_object(path: Path, data: dict[str, list[dict[str, Any]]]) -> None:
    """Write a grouped JSON object to disk."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as file:
        json.dump(data, file, indent=4, ensure_ascii=False)


def append_grouped_json(path: Path, new_data: dict[str, list[dict[str, Any]]]) -> None:
    """Append grouped JSON values to an existing output file."""
    # Keep previous runs and append new batches per language pair
    combined = read_json_object(path)
    for key, values in new_data.items():
        combined.setdefault(key, []).extend(values)
    write_json_object(path, combined)


def report_progress(progress_callback: ProgressCallback | None, message: str) -> None:
    """Send a progress message when a callback is configured."""
    if progress_callback:
        progress_callback(message)


def format_language_pair(language_pair: str) -> str:
    """Format an internal language pair key for user-facing names."""
    parts = language_pair.split("_")
    if len(parts) != 2 or not all(parts):
        raise ValueError(f"Invalid language pair: {language_pair}")
    return f"{parts[0].upper()}->{parts[1].upper()}"


def get_apkg_filename(language_pair: str) -> str:
    """Build the APKG filename for a language pair."""
    return f"{format_language_pair(language_pair)}.apkg"


def get_deck_name(language_pair: str) -> str:
    """Build the Anki deck name for a language pair."""
    return f"{ANKI_PARENT_DECK}::{format_language_pair(language_pair)}"


def run_pipeline(
    db_path: Path,
    api_key: str,
    model: str,
    native_language_code: str,
    batch_size: int,
    cache_path: Path = DEFAULT_CACHE_PATH,
    raw_response_path: Path = DEFAULT_RAW_RESPONSE_PATH,
    anki_cards_path: Path = DEFAULT_ANKI_CARDS_PATH,
    output_dir: Path = DEFAULT_APKG_DIR,
    progress_callback: ProgressCallback | None = None,
) -> PipelineResult:
    """Run the full Kindle-to-Anki workflow."""
    # This orchestration is UI-neutral so the CLI and a future GUI can call the same workflow
    if not db_path.is_file():
        raise FileNotFoundError(
            f"Kindle vocabulary database not found at {db_path}. "
            "Put vocab.db under put_vocab_db_here/vocab.db or pass --db-path."
        )

    # Reading the DB also applies the cache filter
    report_progress(progress_callback, f"Reading Kindle vocabulary database: {db_path}")
    with sqlite3.connect(db_path) as connection:
        words = extract_information(connection, cache_path)
    report_progress(progress_callback, f"Found {len(words)} new words after cache filtering.")

    if not words:
        return PipelineResult(
            words_read=0,
            apkg_paths=[],
            raw_response_path=raw_response_path,
            anki_cards_path=anki_cards_path,
        )

    words_by_language = separate_words_by_language(words)
    prompts = get_all_prompts(words_by_language, native_language_code, batch_size)
    prompt_count = sum(len(prompt_group) for prompt_group in prompts.values())
    report_progress(progress_callback, f"Prepared {prompt_count} Gemini batches with batch size {batch_size}.")
    responses = process_prompt_jobs(prompts, api_key, model, progress_callback)

    # Prompt jobs now contain parsed Gemini responses used for card generation
    report_progress(progress_callback, "Building Anki cards.")
    cards_by_language_pair = prompt_jobs_to_anki_cards(prompts)
    apkg_paths = []
    for language_pair, cards in cards_by_language_pair.items():
        if not cards:
            continue
        output_path = output_dir / get_apkg_filename(language_pair)
        report_progress(progress_callback, f"Writing {output_path}.")
        write_apkg(cards, output_path, get_deck_name(language_pair))
        apkg_paths.append(output_path)

    report_progress(progress_callback, "Writing JSON output files.")
    append_grouped_json(raw_response_path, response_batches_to_dict(responses))
    append_grouped_json(anki_cards_path, anki_cards_to_dict(cards_by_language_pair))

    # Cache only after all outputs are persisted
    report_progress(progress_callback, "Updating processed-word cache.")
    add_words_to_cache(words, cache_path)

    return PipelineResult(
        words_read=len(words),
        apkg_paths=apkg_paths,
        raw_response_path=raw_response_path,
        anki_cards_path=anki_cards_path,
    )
