"""Shopper-turn application service and trace persistence boundary."""

from datetime import UTC, datetime
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
    ConstraintChange,
    ProductRecommendation,
    RecommendationValidation,
    ResolvedConstraints,
    TokenUsage,
    ToolCallTrace,
    TraceError,
    TraceResponse,
)
from salesagent.domain.conversation import (
    ConversationTurn,
    ResolvedConstraintState,
    SessionState,
)
from salesagent.repositories.sessions import InMemorySessionRepository
from salesagent.repositories.traces import InMemoryTraceRepository
from salesagent.services.constraints import (
    ConstraintMergeResult,
    ConstraintStateMerger,
)
from salesagent.services.recommendations import (
    HydratedRecommendation,
    RecommendationHydrationResult,
    RecommendationHydrator,
)

GENERIC_FAILURE_DETAIL = "Sales Agent is temporarily unavailable."

_TERMINAL_ERROR_MESSAGES: dict[OrchestrationErrorCode, str] = {
    "missing_openai_configuration": "Model service is not configured.",
    "openai_authentication_failed": "Model service authentication failed.",
    "openai_invalid_request": "Model service rejected the request.",
    "openai_rate_limited": "Model service rate limit reached.",
    "openai_timeout": "Model service timed out.",
    "openai_unavailable": "Model service is unavailable.",
    "malformed_model_response": "Model response could not be processed.",
    "invalid_tool_evidence": "Tool result evidence could not be processed.",
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
        recommendation_hydrator: RecommendationHydrator,
        session_repository: InMemorySessionRepository | None = None,
        constraint_merger: ConstraintStateMerger | None = None,
    ) -> None:
        self._trace_repository = trace_repository
        self._orchestrator = orchestrator
        self._recommendation_hydrator = recommendation_hydrator
        self._session_repository = session_repository or InMemorySessionRepository()
        self._constraint_merger = constraint_merger or ConstraintStateMerger()

    def chat(self, request: ChatRequest) -> ChatResponse:
        """Run one stateless model turn and persist its safe trace."""
        started_at = perf_counter_ns()
        session_id = request.session_id or str(uuid4())
        trace_id = str(uuid4())
        with self._session_repository.lease(session_id) as lease:
            snapshot = lease.state
            try:
                result = self._orchestrator.run(request.message, snapshot)
            except AgentOrchestrationError as error:
                terminal_error = TraceErrorEvidence(
                    code=error.code,
                    message=_TERMINAL_ERROR_MESSAGES[error.code],
                    tool_call_id=error.tool_call_id,
                )
                trace = self._build_trace(
                    trace_id=trace_id,
                    session_id=session_id,
                    turn_index=lease.turn_index,
                    user_message=request.message,
                    model=self._orchestrator.model,
                    prompt_version=self._orchestrator.prompt_version,
                    usage=error.usage,
                    tool_evidence=error.tool_calls,
                    errors=(*error.errors, terminal_error),
                    started_at=started_at,
                    resolved_constraints=snapshot.resolved_constraints,
                )
                self._trace_repository.store(trace)
                raise ChatServiceError(trace_id=trace_id, code=error.code) from error

            merged = self._constraint_merger.merge(
                snapshot.resolved_constraints,
                result.constraint_updates,
            )
            hydration = self._recommendation_hydrator.hydrate(
                result.nominated_product_ids,
                result.grounded_product_ids,
            )
            recommendations = [
                self._map_recommendation(item) for item in hydration.recommendations
            ]
            response = ChatResponse(
                session_id=session_id,
                trace_id=trace_id,
                message=result.final_text,
                recommendations=recommendations,
                promotion=None,
                pricing=None,
            )
            trace = self._build_trace(
                trace_id=trace_id,
                session_id=session_id,
                turn_index=lease.turn_index,
                user_message=request.message,
                model=result.model,
                prompt_version=result.prompt_version,
                usage=result.usage,
                tool_evidence=result.tool_calls,
                errors=result.errors,
                started_at=started_at,
                hydration=hydration,
                resolved_constraints=merged.state,
                constraint_changes=self._map_changes(snapshot, merged),
            )
            committed_state = SessionState(
                resolved_constraints=merged.state,
                history=snapshot.history,
            ).append_turn(
                ConversationTurn(
                    user_message=request.message,
                    assistant_message=result.final_text,
                    recommended_product_ids=hydration.accepted_product_ids,
                )
            )
            self._trace_repository.store(trace)
            lease.commit(committed_state)
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
        hydration: RecommendationHydrationResult | None = None,
        resolved_constraints: ResolvedConstraintState | None = None,
        constraint_changes: list[ConstraintChange] | None = None,
    ) -> TraceResponse:
        recommendation_validation = (
            RecommendationValidation(
                all_products_exist=hydration.all_products_exist,
                prices_match_catalogue=hydration.prices_match_catalogue,
                urls_match_catalogue=hydration.urls_match_catalogue,
                stock_claims_validated=hydration.stock_claims_validated,
                validation_errors=list(hydration.validation_errors),
            )
            if hydration is not None
            else RecommendationValidation(
                all_products_exist=True,
                prices_match_catalogue=True,
                urls_match_catalogue=True,
                stock_claims_validated=True,
            )
        )
        trace = TraceResponse(
            trace_id=trace_id,
            session_id=session_id,
            timestamp=datetime.now(UTC),
            turn_index=turn_index,
            user_message=user_message,
            model=model,
            prompt_version=prompt_version,
            resolved_constraints=ChatService._map_constraints(
                resolved_constraints or ResolvedConstraintState()
            ),
            constraint_changes=constraint_changes or [],
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
            recommendation_validation=recommendation_validation,
            recommended_product_ids=(
                list(hydration.accepted_product_ids) if hydration is not None else []
            ),
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

    @staticmethod
    def _map_recommendation(
        recommendation: HydratedRecommendation,
    ) -> ProductRecommendation:
        return ProductRecommendation(
            product_id=recommendation.product_id,
            name=recommendation.name,
            price=recommendation.price,
            currency=recommendation.currency,
            product_url=recommendation.product_url,
            availability=recommendation.availability,
            matched_variant=None,
        )

    @staticmethod
    def _map_constraints(state: ResolvedConstraintState) -> ResolvedConstraints:
        return ResolvedConstraints(
            category=state.category,
            activity=state.activity,
            weather=list(state.weather),
            features=list(state.features),
            maximum_price=state.maximum_price,
            colour=state.colour,
            size=state.size,
            season=state.season,
            priority=state.priority,
        )

    @staticmethod
    def _map_changes(
        snapshot: SessionState,
        merged: ConstraintMergeResult,
    ) -> list[ConstraintChange]:
        previous = ChatService._map_constraints(
            snapshot.resolved_constraints
        ).model_dump(mode="json")
        current = ChatService._map_constraints(merged.state).model_dump(mode="json")
        return [
            ConstraintChange(
                field=change.field,
                previous=previous[change.field],
                current=current[change.field],
            )
            for change in merged.changes
        ]
