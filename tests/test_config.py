"""Tests for centrally validated environment-backed settings."""

import pytest

from salesagent.config import Settings


def test_openai_settings_have_safe_phase_four_defaults(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for name in (
        "OPENAI_API_KEY",
        "OPENAI_MODEL",
        "OPENAI_REASONING_EFFORT",
        "OPENAI_MAX_OUTPUT_TOKENS",
        "OPENAI_TIMEOUT_SECONDS",
        "SALESAGENT_ENABLE_EVAL_TRACES",
    ):
        monkeypatch.delenv(name, raising=False)

    settings = Settings.from_environment()

    assert settings.openai_api_key is None
    assert settings.openai_model == "gpt-5.6-terra"
    assert settings.openai_reasoning_effort == "low"
    assert settings.openai_max_output_tokens == 2000
    assert settings.openai_timeout_seconds == 30.0
    assert settings.enable_eval_traces is True


def test_openai_settings_are_read_from_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "  test-key  ")
    monkeypatch.setenv("OPENAI_MODEL", " gpt-5.6-sol ")
    monkeypatch.setenv("OPENAI_REASONING_EFFORT", "HIGH")
    monkeypatch.setenv("OPENAI_MAX_OUTPUT_TOKENS", "4096")
    monkeypatch.setenv("OPENAI_TIMEOUT_SECONDS", "12.5")
    monkeypatch.setenv("SALESAGENT_ENABLE_EVAL_TRACES", "off")

    settings = Settings.from_environment()

    assert settings.openai_api_key == "test-key"
    assert settings.openai_model == "gpt-5.6-sol"
    assert settings.openai_reasoning_effort == "high"
    assert settings.openai_max_output_tokens == 4096
    assert settings.openai_timeout_seconds == 12.5
    assert settings.enable_eval_traces is False


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("OPENAI_MODEL", "   "),
        ("OPENAI_REASONING_EFFORT", "extreme"),
        ("OPENAI_MAX_OUTPUT_TOKENS", "0"),
        ("OPENAI_MAX_OUTPUT_TOKENS", "16001"),
        ("OPENAI_MAX_OUTPUT_TOKENS", "many"),
        ("OPENAI_TIMEOUT_SECONDS", "0"),
        ("OPENAI_TIMEOUT_SECONDS", "121"),
        ("OPENAI_TIMEOUT_SECONDS", "later"),
        ("SALESAGENT_ENABLE_EVAL_TRACES", "sometimes"),
    ],
)
def test_invalid_settings_fail_centrally(
    monkeypatch: pytest.MonkeyPatch, name: str, value: str
) -> None:
    monkeypatch.setenv(name, value)

    with pytest.raises(ValueError, match=name):
        Settings.from_environment()
