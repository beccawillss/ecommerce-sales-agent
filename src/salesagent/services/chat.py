"""Shopper-turn application service and trace persistence boundary."""

from datetime import UTC, datetime
from threading import Lock
from time import perf_counter_ns
from uuid import uuid4

from salesagent.agent.orchestrator import (
    AgentOrchestrationError,
    AgentOrchestrator,
    OrchestrationErrorCode,
    ToolTraceEvidence,
    TraceErrorEvidence,
)
from salesagent.agent.responses_client import ResponseUsage
from salesagent.api.models import (
    ChatRequest,
    ChatResponse,
    RecommendationValidation,
    ResolvedConstraints,
    TokenUsage,
    ToolCallTrace,
    TraceError,
    TraceResponse,
)
from salesagent.repositories.traces import InMemoryTraceRepository

GENERIC_FAILURE_DETAIL = "Sales Agent is temporarily unavailable."

_TERMINAL_ERROR_MESSAGES: dict[OrchestrationErrorCode, str] = {
    "missing_openai_configuration": "Model service is not configured.",
    "openai_authentication_failed": "Model service authentication failed.",
    "openai_invalid_request": "Model service rejected the request.",
    "openai_rate_limited": "Model service rate limit reached.",
    "openai_timeout": "Model service timed out.",
    "openai_unavailable": "Model service is unavailable.",
    "malformed_model_response": "Model response could not be processed.",
    "orchestration_limit_reached": "Agent orchestration limit reached.",
}


class ChatServiceError(RuntimeError):
    """Safe terminal chat failure with an internal trace identifier."""

    def __init__(
        self,
        *,
        trace_id: str,
        code: OrchestrationErrorCode,
    ) -> None:
        super().__init__(code)
        self.trace_id = trace_id
        self.code = code


class ChatService:
    """Own session turns, API response assembly, and trace persistence."""

    def __init__(
        self,
        trace_repository: InMemoryTraceRepository,
        orchestrator: AgentOrchestrator,
    ) -> None:
        self._trace_repository = trace_repository
        self._orchestrator = orchestrator
        self._turn_indices: dict[str, int] = {}
        self._turn_lock = Lock()

    def chat(self, request: ChatRequest) -> ChatResponse:
        """Run one stateless model turn and persist its safe trace."""
        started_at = perf_counter_ns()
        session_id = request.session_id or str(uuid4())
        trace_id = str(uuid4())
        turn_index = self._next_turn_index(session_id)

        try:
            result = self._orchestrator.run(request.message)
        except AgentOrchestrationError as error:
            terminal_error = TraceErrorEvidence(
                code=error.code,
                message=_TERMINAL_ERROR_MESSAGES[error.code],
                tool_call_id=error.tool_call_id,
            )
            trace = self._build_trace(
                trace_id=trace_id,
                session_id=session_id,
                turn_index=turn_index,
                user_message=request.message,
                model=self._orchestrator.model,
                prompt_version=self._orchestrator.prompt_version,
                usage=error.usage,
                tool_evidence=error.tool_calls,
                errors=(*error.errors, terminal_error),
                started_at=started_at,
            )
            self._trace_repository.store(trace)
            raise ChatServiceError(trace_id=trace_id, code=error.code) from error

        response = ChatResponse(
            session_id=session_id,
            trace_id=trace_id,
            message=result.final_text,
            recommendations=[],
            promotion=None,
            pricing=None,
        )
        trace = self._build_trace(
            trace_id=trace_id,
            session_id=session_id,
            turn_index=turn_index,
            user_message=request.message,
            model=result.model,
            prompt_version=result.prompt_version,
            usage=result.usage,
            tool_evidence=result.tool_calls,
            errors=result.errors,
            started_at=started_at,
        )
        self._trace_repository.store(trace)
        return response

    @staticmethod
    def _build_trace(
        *,
        trace_id: str,
        session_id: str,
        turn_index: int,
        user_message: str,
        model: str,
        prompt_version: str,
        usage: ResponseUsage,
        tool_evidence: tuple[ToolTraceEvidence, ...],
        errors: tuple[TraceErrorEvidence, ...],
        started_at: int,
    ) -> TraceResponse:
        trace = TraceResponse(
            trace_id=trace_id,
            session_id=session_id,
            timestamp=datetime.now(UTC),
            turn_index=turn_index,
            user_message=user_message,
            model=model,
            prompt_version=prompt_version,
            resolved_constraints=ResolvedConstraints(),
            constraint_changes=[],
            tool_calls=[
                ToolCallTrace(
                    sequence=sequence,
                    tool_call_id=item.call_id,
                    tool_name=item.tool_name,
                    arguments=item.arguments,
                    result=item.result,
                    status=item.status,
                    duration_ms=item.duration_ms,
                )
                for sequence, item in enumerate(tool_evidence, start=1)
            ],
            recommendation_validation=RecommendationValidation(
                all_products_exist=True,
                prices_match_catalogue=True,
                urls_match_catalogue=True,
                stock_claims_validated=True,
            ),
            recommended_product_ids=[],
            promotion=None,
            pricing=None,
            latency_ms=0,
            token_usage=TokenUsage(
                input_tokens=usage.input_tokens,
                output_tokens=usage.output_tokens,
                total_tokens=usage.total_tokens,
            ),
            errors=[
                TraceError(
                    code=error.code,
                    message=error.message,
                    tool_call_id=error.tool_call_id,
                )
                for error in errors
            ],
        )
        latency_ms = (perf_counter_ns() - started_at) // 1_000_000
        return trace.model_copy(update={"latency_ms": latency_ms})

    def _next_turn_index(self, session_id: str) -> int:
        with self._turn_lock:
            turn_index = self._turn_indices.get(session_id, 0) + 1
            self._turn_indices[session_id] = turn_index
            return turn_index
