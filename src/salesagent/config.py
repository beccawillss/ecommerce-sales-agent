"""Environment-backed application configuration."""

import os
from dataclasses import dataclass
from typing import Literal, Self, cast

TRACE_SETTING = "SALESAGENT_ENABLE_EVAL_TRACES"
OPENAI_API_KEY_SETTING = "OPENAI_API_KEY"
OPENAI_MODEL_SETTING = "OPENAI_MODEL"
OPENAI_REASONING_EFFORT_SETTING = "OPENAI_REASONING_EFFORT"
OPENAI_MAX_OUTPUT_TOKENS_SETTING = "OPENAI_MAX_OUTPUT_TOKENS"
OPENAI_TIMEOUT_SECONDS_SETTING = "OPENAI_TIMEOUT_SECONDS"

DEFAULT_OPENAI_MODEL = "gpt-5.6-terra"
DEFAULT_OPENAI_MAX_OUTPUT_TOKENS = 2000
DEFAULT_OPENAI_TIMEOUT_SECONDS = 30.0
MAX_OPENAI_OUTPUT_TOKENS = 16_000
MAX_OPENAI_TIMEOUT_SECONDS = 120.0

ReasoningEffort = Literal["none", "low", "medium", "high", "xhigh", "max"]
_REASONING_EFFORTS = frozenset({"none", "low", "medium", "high", "xhigh", "max"})
_TRUE_VALUES = frozenset({"1", "true", "yes", "on"})
_FALSE_VALUES = frozenset({"0", "false", "no", "off"})


@dataclass(frozen=True, slots=True)
class Settings:
    """Configuration required to assemble the application."""

    enable_eval_traces: bool = True
    openai_api_key: str | None = None
    openai_model: str = DEFAULT_OPENAI_MODEL
    openai_reasoning_effort: ReasoningEffort = "low"
    openai_max_output_tokens: int = DEFAULT_OPENAI_MAX_OUTPUT_TOKENS
    openai_timeout_seconds: float = DEFAULT_OPENAI_TIMEOUT_SECONDS

    @classmethod
    def from_environment(cls) -> Self:
        """Read and validate all supported settings once during assembly."""
        api_key = os.getenv(OPENAI_API_KEY_SETTING)
        model = os.getenv(OPENAI_MODEL_SETTING, DEFAULT_OPENAI_MODEL).strip()
        reasoning_effort = (
            os.getenv(OPENAI_REASONING_EFFORT_SETTING, "low").strip().casefold()
        )

        if not model:
            raise ValueError(f"{OPENAI_MODEL_SETTING} must not be blank")
        if reasoning_effort not in _REASONING_EFFORTS:
            allowed = ", ".join(sorted(_REASONING_EFFORTS))
            raise ValueError(
                f"{OPENAI_REASONING_EFFORT_SETTING} must be one of: {allowed}"
            )

        return cls(
            enable_eval_traces=_read_bool(TRACE_SETTING, default=True),
            openai_api_key=api_key.strip() if api_key and api_key.strip() else None,
            openai_model=model,
            openai_reasoning_effort=cast(ReasoningEffort, reasoning_effort),
            openai_max_output_tokens=_read_int(
                OPENAI_MAX_OUTPUT_TOKENS_SETTING,
                default=DEFAULT_OPENAI_MAX_OUTPUT_TOKENS,
                maximum=MAX_OPENAI_OUTPUT_TOKENS,
            ),
            openai_timeout_seconds=_read_float(
                OPENAI_TIMEOUT_SECONDS_SETTING,
                default=DEFAULT_OPENAI_TIMEOUT_SECONDS,
                maximum=MAX_OPENAI_TIMEOUT_SECONDS,
            ),
        )


def _read_bool(name: str, *, default: bool) -> bool:
    raw_value = os.getenv(name, str(default)).strip().casefold()
    if raw_value in _TRUE_VALUES:
        return True
    if raw_value in _FALSE_VALUES:
        return False
    raise ValueError(f"{name} must be one of: true, false, 1, 0, yes, no, on, off")


def _read_int(name: str, *, default: int, maximum: int) -> int:
    raw_value = os.getenv(name, str(default)).strip()
    try:
        value = int(raw_value)
    except ValueError as error:
        raise ValueError(f"{name} must be an integer") from error
    if not 1 <= value <= maximum:
        raise ValueError(f"{name} must be between 1 and {maximum}")
    return value


def _read_float(name: str, *, default: float, maximum: float) -> float:
    raw_value = os.getenv(name, str(default)).strip()
    try:
        value = float(raw_value)
    except ValueError as error:
        raise ValueError(f"{name} must be a number") from error
    if not 0 < value <= maximum:
        raise ValueError(f"{name} must be greater than 0 and at most {maximum:g}")
    return value
