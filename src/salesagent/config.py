"""Minimal environment-backed application configuration."""

import os
from dataclasses import dataclass
from typing import Self

TRACE_SETTING = "SALESAGENT_ENABLE_EVAL_TRACES"
_TRUE_VALUES = frozenset({"1", "true", "yes", "on"})
_FALSE_VALUES = frozenset({"0", "false", "no", "off"})


@dataclass(frozen=True, slots=True)
class Settings:
    """Configuration required to assemble the Phase 2 application."""

    enable_eval_traces: bool = True

    @classmethod
    def from_environment(cls) -> Self:
        """Read trace exposure from the environment, defaulting on locally."""
        raw_value = os.getenv(TRACE_SETTING, "true").strip().casefold()
        if raw_value in _TRUE_VALUES:
            return cls(enable_eval_traces=True)
        if raw_value in _FALSE_VALUES:
            return cls(enable_eval_traces=False)
        raise ValueError(
            f"{TRACE_SETTING} must be one of: true, false, 1, 0, yes, no, on, off"
        )
