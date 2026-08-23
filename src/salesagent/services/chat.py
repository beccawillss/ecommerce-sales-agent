"""Deterministic Phase 2 chat application service."""

from datetime import UTC, datetime
from threading import Lock
from time import perf_counter_ns
from uuid import uuid4

from salesagent.api.models import (
    ChatRequest,
    ChatResponse,
    RecommendationValidation,
    ResolvedConstraints,
    TokenUsage,
    TraceResponse,
)
from salesagent.repositories.traces import InMemoryTraceRepository

STUB_MESSAGE = "Sales Agent is not configured yet."


class ChatService:
    """Fulfil the Phase 2 chat boundary with deterministic stub behavior."""

    def __init__(self, trace_repository: InMemoryTraceRepository) -> None:
        self._trace_repository = trace_repository
        self._turn_indices: dict[str, int] = {}
        self._turn_lock = Lock()

    def chat(self, request: ChatRequest) -> ChatResponse:
        """Create a deterministic placeholder response and matching trace."""
        started_at = perf_counter_ns()
        session_id = (
            request.session_id if request.session_id is not None else str(uuid4())
        )
        trace_id = str(uuid4())
        turn_index = self._next_turn_index(session_id)

        response = ChatResponse(
            session_id=session_id,
            trace_id=trace_id,
            message=STUB_MESSAGE,
            recommendations=[],
        )
        trace = TraceResponse(
            trace_id=trace_id,
            session_id=session_id,
            timestamp=datetime.now(UTC),
            turn_index=turn_index,
            user_message=request.message,
            model="stub",
            prompt_version="none",
            resolved_constraints=ResolvedConstraints(),
            constraint_changes=[],
            tool_calls=[],
            recommendation_validation=RecommendationValidation(
                all_products_exist=True,
                prices_match_catalogue=True,
                urls_match_catalogue=True,
                stock_claims_validated=True,
            ),
            recommended_product_ids=[],
            latency_ms=(perf_counter_ns() - started_at) // 1_000_000,
            token_usage=TokenUsage(
                input_tokens=0,
                output_tokens=0,
                total_tokens=0,
            ),
            errors=[],
        )
        self._trace_repository.store(trace)
        return response

    def _next_turn_index(self, session_id: str) -> int:
        with self._turn_lock:
            turn_index = self._turn_indices.get(session_id, 0) + 1
            self._turn_indices[session_id] = turn_index
            return turn_index
