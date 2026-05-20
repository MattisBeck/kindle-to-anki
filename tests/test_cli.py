from pathlib import Path

from pytest_mock import MockerFixture

from kindle_to_anki import cli
from kindle_to_anki.config import (
    BATCH_SIZE,
    GEMINI_API_KEY,
    GEMINI_MODEL,
    NATIVE_LANGUAGE_CODE,
    AppConfig,
    GeminiModel,
    load_app_config,
    read_env_values,
    set_api_key,
    set_native_language,
)
from kindle_to_anki.llm_translator import DEFAULT_GEMINI_MODEL
from kindle_to_anki.models import GeminiHighDemandError
from kindle_to_anki.pipeline import PipelineResult


def test_config_interactive_writes_env(mocker: MockerFixture, tmp_path: Path) -> None:
    env_path = tmp_path / ".env"
    models = [GeminiModel("models/gemini-2.5-flash", "Gemini 2.5 Flash")]
    mocker.patch("kindle_to_anki.cli.get_generate_content_models", return_value=models)
    answers = iter(["de", "10", ""])

    config = cli.configure_interactively(
        env_path=env_path,
        input_func=lambda _: next(answers),
        secret_input_func=lambda _: "secret",
    )

    values = read_env_values(env_path)
    assert config.api_key == "secret"
    assert values[GEMINI_API_KEY] == "secret"
    assert values[NATIVE_LANGUAGE_CODE] == "de"
    assert values[BATCH_SIZE] == "10"
    assert values[GEMINI_MODEL] == "models/gemini-2.5-flash"


def test_first_run_auto_configures_then_runs_pipeline(mocker: MockerFixture, tmp_path: Path) -> None:
    env_path = tmp_path / ".env"
    configured = AppConfig("secret", "models/gemini-test", "de", 10, env_path)
    configure_mock = mocker.patch("kindle_to_anki.cli.configure_interactively", return_value=configured)
    run_mock = mocker.patch(
        "kindle_to_anki.cli.run_pipeline",
        return_value=PipelineResult(
            words_read=0,
            apkg_paths=[],
            raw_response_path=tmp_path / "raw.json",
            anki_cards_path=tmp_path / "cards.json",
        ),
    )

    exit_code = cli.main([], env_path=env_path)

    assert exit_code == 0
    configure_mock.assert_called_once_with(env_path)
    run_mock.assert_called_once()


def test_set_api_key_validates_and_writes(mocker: MockerFixture, tmp_path: Path) -> None:
    env_path = tmp_path / ".env"
    mocker.patch(
        "kindle_to_anki.cli.get_generate_content_models",
        return_value=[GeminiModel("models/gemini-test")],
    )

    exit_code = cli.main(["--set-api-key", "secret"], env_path=env_path)

    assert exit_code == 0
    assert read_env_values(env_path)[GEMINI_API_KEY] == "secret"


def test_set_gemini_model_requires_generate_content_model(mocker: MockerFixture, tmp_path: Path) -> None:
    env_path = tmp_path / ".env"
    set_api_key("secret", env_path)
    mocker.patch(
        "kindle_to_anki.cli.get_generate_content_models",
        return_value=[GeminiModel("models/gemini-test")],
    )

    exit_code = cli.main(["--set-gemini-model", "gemini-test"], env_path=env_path)

    assert exit_code == 0
    assert read_env_values(env_path)[GEMINI_MODEL] == "models/gemini-test"


def test_set_gemini_model_rejects_missing_model(mocker: MockerFixture, tmp_path: Path) -> None:
    env_path = tmp_path / ".env"
    set_api_key("secret", env_path)
    mocker.patch(
        "kindle_to_anki.cli.get_generate_content_models",
        return_value=[GeminiModel("models/gemini-test")],
    )

    exit_code = cli.main(["--set-gemini-model", "missing"], env_path=env_path)

    assert exit_code == 1
    assert read_env_values(env_path)[GEMINI_MODEL] == DEFAULT_GEMINI_MODEL


def test_status_reports_missing_api_key(tmp_path: Path) -> None:
    env_path = tmp_path / ".env"
    set_native_language("de", env_path)

    assert cli.main(["--status"], env_path=env_path) == 1


def test_status_validates_api_key(mocker: MockerFixture, tmp_path: Path) -> None:
    env_path = tmp_path / ".env"
    set_api_key("secret", env_path)
    set_native_language("de", env_path)
    mocker.patch(
        "kindle_to_anki.cli.get_generate_content_models",
        return_value=[GeminiModel("models/gemini-test")],
    )

    assert cli.main(["--status"], env_path=env_path) == 0


def test_pipeline_run_uses_overrides(mocker: MockerFixture, tmp_path: Path) -> None:
    env_path = tmp_path / ".env"
    db_path = tmp_path / "vocab.db"
    set_api_key("secret", env_path)
    set_native_language("de", env_path)
    run_mock = mocker.patch(
        "kindle_to_anki.cli.run_pipeline",
        return_value=PipelineResult(
            words_read=0,
            apkg_paths=[],
            raw_response_path=tmp_path / "raw.json",
            anki_cards_path=tmp_path / "cards.json",
        ),
    )

    exit_code = cli.main(
        ["--db-path", str(db_path), "--native-language", "en", "--batch-size", "3"],
        env_path=env_path,
    )

    assert exit_code == 0
    call = run_mock.call_args.kwargs
    assert call["db_path"] == db_path
    assert call["native_language_code"] == "en"
    assert call["batch_size"] == 3
    assert call["progress_callback"] is None
    assert load_app_config(env_path).native_language_code == "de"


def test_pipeline_run_uses_progress_callback_when_verbose(mocker: MockerFixture, tmp_path: Path) -> None:
    env_path = tmp_path / ".env"
    db_path = tmp_path / "vocab.db"
    set_api_key("secret", env_path)
    set_native_language("de", env_path)
    run_mock = mocker.patch(
        "kindle_to_anki.cli.run_pipeline",
        return_value=PipelineResult(
            words_read=0,
            apkg_paths=[],
            raw_response_path=tmp_path / "raw.json",
            anki_cards_path=tmp_path / "cards.json",
        ),
    )

    exit_code = cli.main(["--db-path", str(db_path), "-v"], env_path=env_path)

    assert exit_code == 0
    assert callable(run_mock.call_args.kwargs["progress_callback"])


def test_cli_handles_gemini_high_demand_without_traceback(
    mocker: MockerFixture,
    tmp_path: Path,
    capsys,
) -> None:
    env_path = tmp_path / ".env"
    set_api_key("secret", env_path)
    set_native_language("de", env_path)
    mocker.patch(
        "kindle_to_anki.cli.run_pipeline",
        side_effect=GeminiHighDemandError(503, "This model is currently experiencing high demand."),
    )

    exit_code = cli.main([], env_path=env_path)

    captured = capsys.readouterr()
    assert exit_code == 1
    assert "Gemini is currently overloaded after all retry attempts." in captured.err
    assert "This model is currently experiencing high demand." in captured.err
    assert "Traceback" not in captured.err
