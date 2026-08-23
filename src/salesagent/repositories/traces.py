"""Minimal in-memory storage for completed chat-turn traces."""

from threading import Lock

from salesagent.api.models import TraceResponse


class InMemoryTraceRepository:
    """Store traces for the lifetime of one application process."""

    def __init__(self) -> None:
        self._traces: dict[str, TraceResponse] = {}
        self._lock = Lock()

    def store(self, trace: TraceResponse) -> None:
        """Store or replace a trace under its generated unique ID."""
        with self._lock:
            self._traces[trace.trace_id] = trace

    def get(self, trace_id: str) -> TraceResponse | None:
        """Retrieve a trace, or ``None`` when its ID is unknown."""
        with self._lock:
            return self._traces.get(trace_id)
