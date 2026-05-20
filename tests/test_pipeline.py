import sqlite3
from pathlib import Path

import pytest
from pytest_mock import MockerFixture

from kindle_to_anki.db_reader import get_cache_set
from kindle_to_anki.models import ForeignVocabularyBatch, NativeDefinitionBatch, PromptJob, PromptType
from kindle_to_anki.pipeline import (
    append_grouped_json,
    format_language_pair,
    get_apkg_filename,
    get_deck_name,
    read_json_object,
    run_pipeline,
)


def create_vocab_db(db_path: Path) -> None:
    sql_location = Path(__file__).parent / "data" / "mock_vocab.sql"
    with sqlite3.connect(db_path) as connection:
        connection.executescript(sql_location.read_text(encoding="utf-8"))


def build_native_batch(job: PromptJob) -> NativeDefinitionBatch:
    return NativeDefinitionBatch.model_validate(
        {
            "items": [
                {
                    "item_index": index,
                    "lemma": word.stem,
                    "definition": f"Definition for {word.stem}",
                    "ambiguity": "low",
                    "anchor": word.word,
                    "confidence": 1.0,
                }
                for index, word in enumerate(job.words)
            ]
        }
    )


def build_foreign_batch(job: PromptJob) -> ForeignVocabularyBatch:
    return ForeignVocabularyBatch.model_validate(
        {
            "items": [
                {
                    "item_index": index,
                    "lemma": word.stem,
                    "definition": f"Definition for {word.stem}",
                    "ambiguity": "low",
                    "anchor": word.word,
                    "confidence": 1.0,
                    "gloss": f"Gloss for {word.stem}",
                }
                for index, word in enumerate(job.words)
            ]
        }
    )


def fake_process_prompt_jobs(prompts: dict[str, list[PromptJob]], *_args: object) -> dict[str, list[object]]:
    results: dict[str, list[object]] = {}
    for jobs in prompts.values():
        for job in jobs:
            batch = build_native_batch(job) if job.type == PromptType.NATIVE_DEFINITION else build_foreign_batch(job)
            job.parsed_response = batch
            language_pair = f"{job.native_language_code}_{job.source_language_code}"
            results.setdefault(language_pair, []).append(batch)
    return results


def test_append_grouped_json_is_cumulative(tmp_path: Path) -> None:
    path = tmp_path / "data.json"
    append_grouped_json(path, {"de_de": [{"lemma": "alt"}]})
    append_grouped_json(path, {"de_de": [{"lemma": "neu"}], "en_de": [{"lemma": "cloud"}]})

    assert read_json_object(path) == {
        "de_de": [{"lemma": "alt"}, {"lemma": "neu"}],
        "en_de": [{"lemma": "cloud"}],
    }


def test_language_pair_output_names() -> None:
    assert format_language_pair("de_de") == "DE->DE"
    assert get_apkg_filename("en_de") == "EN->DE.apkg"
    assert get_deck_name("de_en") == "Kindle::DE->EN"


def test_run_pipeline_missing_db(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        run_pipeline(
            db_path=tmp_path / "missing.db",
            api_key="secret",
            model="models/gemini-test",
            native_language_code="de",
            batch_size=10,
            cache_path=tmp_path / "cache.json",
            raw_response_path=tmp_path / "raw.json",
            anki_cards_path=tmp_path / "cards.json",
            output_dir=tmp_path,
        )


def test_run_pipeline_writes_json_and_apkgs(mocker: MockerFixture, tmp_path: Path) -> None:
    db_path = tmp_path / "vocab.db"
    apkg_dir = tmp_path / "apkg"
    json_dir = tmp_path / "json"
    create_vocab_db(db_path)
    mocker.patch("kindle_to_anki.pipeline.process_prompt_jobs", side_effect=fake_process_prompt_jobs)
    write_apkg_mock = mocker.patch("kindle_to_anki.pipeline.write_apkg")

    result = run_pipeline(
        db_path=db_path,
        api_key="secret",
        model="models/gemini-test",
        native_language_code="de",
        batch_size=10,
        cache_path=json_dir / "cache.json",
        raw_response_path=json_dir / "raw.json",
        anki_cards_path=json_dir / "cards.json",
        output_dir=apkg_dir,
    )

    raw = read_json_object(json_dir / "raw.json")
    cards = read_json_object(json_dir / "cards.json")
    assert result.words_read == 10
    assert set(raw) == {"de_de", "de_en"}
    assert set(cards) == {"de_de", "en_de", "de_en"}
    assert sorted(result.apkg_paths) == [
        apkg_dir / "DE->DE.apkg",
        apkg_dir / "DE->EN.apkg",
        apkg_dir / "EN->DE.apkg",
    ]
    assert write_apkg_mock.call_count == 3
    assert sorted(call.args[1] for call in write_apkg_mock.call_args_list) == [
        apkg_dir / "DE->DE.apkg",
        apkg_dir / "DE->EN.apkg",
        apkg_dir / "EN->DE.apkg",
    ]
    assert sorted(call.args[2] for call in write_apkg_mock.call_args_list) == [
        "Kindle::DE->DE",
        "Kindle::DE->EN",
        "Kindle::EN->DE",
    ]
    assert json_dir.is_dir()
    assert len(get_cache_set(json_dir / "cache.json")) == 10


def test_run_pipeline_reports_progress(mocker: MockerFixture, tmp_path: Path) -> None:
    db_path = tmp_path / "vocab.db"
    messages: list[str] = []
    create_vocab_db(db_path)
    mocker.patch("kindle_to_anki.pipeline.process_prompt_jobs", side_effect=fake_process_prompt_jobs)
    mocker.patch("kindle_to_anki.pipeline.write_apkg")

    run_pipeline(
        db_path=db_path,
        api_key="secret",
        model="models/gemini-test",
        native_language_code="de",
        batch_size=10,
        cache_path=tmp_path / "cache.json",
        raw_response_path=tmp_path / "raw.json",
        anki_cards_path=tmp_path / "cards.json",
        output_dir=tmp_path,
        progress_callback=messages.append,
    )

    assert messages[0].startswith("Reading Kindle vocabulary database:")
    assert any("Found 10 new words" in message for message in messages)
    assert "Prepared 2 Gemini batches with batch size 10." in messages
    assert "Building Anki cards." in messages
    assert "Writing JSON output files." in messages


def test_run_pipeline_does_not_cache_when_processing_fails(mocker: MockerFixture, tmp_path: Path) -> None:
    db_path = tmp_path / "vocab.db"
    cache_path = tmp_path / "cache.json"
    create_vocab_db(db_path)
    mocker.patch("kindle_to_anki.pipeline.process_prompt_jobs", side_effect=ValueError("invalid response"))

    with pytest.raises(ValueError):
        run_pipeline(
            db_path=db_path,
            api_key="secret",
            model="models/gemini-test",
            native_language_code="de",
            batch_size=2,
            cache_path=cache_path,
            raw_response_path=tmp_path / "raw.json",
            anki_cards_path=tmp_path / "cards.json",
            output_dir=tmp_path,
        )

    assert get_cache_set(cache_path) == set()
    assert not (tmp_path / "raw.json").exists()
    assert not (tmp_path / "cards.json").exists()


def test_run_pipeline_does_not_cache_when_apkg_write_fails(mocker: MockerFixture, tmp_path: Path) -> None:
    db_path = tmp_path / "vocab.db"
    cache_path = tmp_path / "cache.json"
    create_vocab_db(db_path)
    mocker.patch("kindle_to_anki.pipeline.process_prompt_jobs", side_effect=fake_process_prompt_jobs)
    mocker.patch("kindle_to_anki.pipeline.write_apkg", side_effect=ValueError("cannot write deck"))

    with pytest.raises(ValueError):
        run_pipeline(
            db_path=db_path,
            api_key="secret",
            model="models/gemini-test",
            native_language_code="de",
            batch_size=10,
            cache_path=cache_path,
            raw_response_path=tmp_path / "raw.json",
            anki_cards_path=tmp_path / "cards.json",
            output_dir=tmp_path,
        )

    assert get_cache_set(cache_path) == set()
