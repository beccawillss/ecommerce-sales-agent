"""Tests for chat response assembly and safe trace persistence."""

import json
from collections.abc import Iterable, Mapping
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Event

import pytest

from salesagent.agent.final_output import (
    ConstraintUpdates,
    MoneyTextUpdate,
    TextUpdate,
)
from salesagent.agent.instructions import DEVELOPER_INSTRUCTIONS
from salesagent.agent.orchestrator import AgentOrchestrator
from salesagent.agent.responses_client import (
    FunctionCall,
    ModelResponse,
    ResponseRequest,
    ResponsesClientError,
    ResponseUsage,
)
from salesagent.agent.tools.dispatcher import ToolDispatcher
from salesagent.agent.tools.models import ToolExecutionResult
from salesagent.api.models import ChatRequest
from salesagent.domain.models import DiscountValidationResult
from salesagent.repositories.products import ProductRepository
from salesagent.repositories.promotions import PromotionRepository
from salesagent.repositories.sessions import InMemorySessionRepository
from salesagent.repositories.traces import InMemoryTraceRepository
from salesagent.services.chat import ChatService, ChatServiceError
from salesagent.services.commerce import CommerceService
from salesagent.services.pricing import (
    PromotionPricingError,
    PromotionPricingOutcome,
    PromotionPricingService,
)
from salesagent.services.recommendations import (
    HydratedRecommendation,
    RecommendationHydrator,
)
from tests.fakes import ScriptedResponsesClient, final_output_json

ROOT = Path(__file__).resolve().parents[1]


class FailingResponsesClient:
    """Raise a safe adapter error chained from recognizable provider text."""

    def create_response(self, request: ResponseRequest) -> ModelResponse:
        try:
            raise RuntimeError("provider-secret-and-authorization-header")
        except RuntimeError as error:
            raise ResponsesClientError("openai_unavailable") from error


class InvalidEvidenceDispatcher(ToolDispatcher):
    def dispatch(
        self, tool_name: str, arguments: Mapping[str, object]
    ) -> ToolExecutionResult:
        return ToolExecutionResult(
            tool_name=tool_name,
            success=True,
            arguments=dict(arguments),
            data={"unsafe": "raw secret tool payload"},
            error=None,
            duration_ms=0,
        )


class FailingPromotionPricingService(PromotionPricingService):
    """Return the service's fixed safe calculation-failure outcome."""

    def resolve(
        self,
        *,
        nominated_promotion_code: str | None,
        grounded_promotions: Iterable[DiscountValidationResult],
        recommendations: Iterable[HydratedRecommendation],
    ) -> PromotionPricingOutcome:
        del nominated_promotion_code, recommendations
        promotion = tuple(grounded_promotions)[0]
        return PromotionPricingOutcome(
            promotion=promotion,
            pricing=None,
            errors=(
                PromotionPricingError(
                    code="pricing_calculation_failed",
                    message="Authoritative pricing could not be calculated safely.",
                ),
            ),
        )


def service_for(
    model_client: ScriptedResponsesClient,
    pricing_service: PromotionPricingService | None = None,
) -> tuple[ChatService, InMemoryTraceRepository]:
    commerce = CommerceService(
        ProductRepository(ROOT / "data" / "products.json"),
        PromotionRepository(ROOT / "data" / "discounts.json"),
    )
    repository = InMemoryTraceRepository()
    orchestrator = AgentOrchestrator(
        responses_client=model_client,
        dispatcher=ToolDispatcher(commerce),
        model="gpt-5.6-terra",
        reasoning_effort="low",
        max_output_tokens=2000,
    )
    return (
        ChatService(
            repository,
            orchestrator,
            RecommendationHydrator(commerce),
            pricing_service or PromotionPricingService(),
        ),
        repository,
    )


def constraint_updates(**values: object) -> ConstraintUpdates:
    payload = ConstraintUpdates.retain_all().model_dump()
    payload.update(values)
    return ConstraintUpdates.model_validate(payload)


def stateful_service_for(
    model_client: ScriptedResponsesClient,
) -> tuple[ChatService, InMemoryTraceRepository, InMemorySessionRepository]:
    commerce = CommerceService(
        ProductRepository(ROOT / "data" / "products.json"),
        PromotionRepository(ROOT / "data" / "discounts.json"),
    )
    traces = InMemoryTraceRepository()
    sessions = InMemorySessionRepository()
    orchestrator = AgentOrchestrator(
        responses_client=model_client,
        dispatcher=ToolDispatcher(commerce),
        model="gpt-5.6-terra",
        reasoning_effort="low",
        max_output_tokens=2000,
    )
    return (
        ChatService(
            traces,
            orchestrator,
            RecommendationHydrator(commerce),
            PromotionPricingService(),
            sessions,
        ),
        traces,
        sessions,
    )


def test_chat_service_persists_ordered_authoritative_tool_trace() -> None:
    model_client = ScriptedResponsesClient(
        [
            ModelResponse(
                response_id="resp-tool",
                output_text="",
                function_calls=(
                    FunctionCall(
                        call_id="call-product",
                        name="get_product",
                        arguments_json='{"product_id":"JKT-001"}',
                    ),
                ),
                usage=ResponseUsage(input_tokens=10, output_tokens=3, total_tokens=13),
                status="completed",
            ),
            ModelResponse(
                response_id="resp-final",
                output_text=final_output_json(
                    "The verified jacket costs £145.", ["jkt-001"]
                ),
                function_calls=(),
                usage=ResponseUsage(input_tokens=8, output_tokens=5, total_tokens=13),
                status="completed",
            ),
        ]
    )
    commerce = CommerceService(
        ProductRepository(ROOT / "data" / "products.json"),
        PromotionRepository(ROOT / "data" / "discounts.json"),
    )
    repository = InMemoryTraceRepository()
    orchestrator = AgentOrchestrator(
        responses_client=model_client,
        dispatcher=ToolDispatcher(commerce),
        model="gpt-5.6-terra",
        reasoning_effort="low",
        max_output_tokens=2000,
    )
    service = ChatService(
        repository,
        orchestrator,
        RecommendationHydrator(commerce),
        PromotionPricingService(),
    )

    response = service.chat(
        ChatRequest(session_id="session-trace", message="Tell me about JKT-001")
    )
    trace = repository.get(response.trace_id)

    assert response.message == "The verified jacket costs £145."
    assert len(response.recommendations) == 1
    recommendation = response.recommendations[0]
    assert recommendation.product_id == "JKT-001"
    assert recommendation.name == "Apex Alpine Waterproof Jacket"
    assert str(recommendation.price) == "145.00"
    assert recommendation.currency == "GBP"
    assert recommendation.product_url == "/products/apex-alpine"
    assert recommendation.availability == "partial"
    assert recommendation.matched_variant is None
    assert response.promotion is None
    assert response.pricing is None
    assert trace is not None
    assert trace.session_id == "session-trace"
    assert trace.turn_index == 1
    assert trace.model == "gpt-5.6-terra"
    assert trace.prompt_version == "phase7-v1"
    assert trace.token_usage.input_tokens == 18
    assert trace.token_usage.output_tokens == 8
    assert trace.token_usage.total_tokens == 26
    assert trace.latency_ms >= 0
    assert len(trace.tool_calls) == 1
    tool_call = trace.tool_calls[0]
    assert tool_call.sequence == 1
    assert tool_call.tool_call_id == "call-product"
    assert tool_call.tool_name == "get_product"
    assert tool_call.arguments == {"product_id": "JKT-001"}
    assert tool_call.result["success"] is True
    assert tool_call.result["data"]["price"] == "145.00"
    assert tool_call.status == "success"
    assert tool_call.duration_ms >= 0
    assert trace.errors == []
    assert trace.recommended_product_ids == ["JKT-001"]
    assert trace.recommendation_validation.model_dump() == {
        "all_products_exist": True,
        "prices_match_catalogue": True,
        "urls_match_catalogue": True,
        "stock_claims_validated": True,
        "validation_errors": [],
    }
    assert trace.resolved_constraints.model_dump() == {
        "category": None,
        "activity": None,
        "weather": [],
        "features": [],
        "maximum_price": None,
        "colour": None,
        "size": None,
        "season": None,
        "priority": None,
    }
    serialized = json.dumps(trace.model_dump(mode="json"))
    assert DEVELOPER_INSTRUCTIONS not in serialized
    assert "reasoning" not in serialized.casefold()
    assert "api_key" not in serialized.casefold()


def test_chat_service_persists_safe_failure_trace_before_raising() -> None:
    commerce = CommerceService(
        ProductRepository(ROOT / "data" / "products.json"),
        PromotionRepository(ROOT / "data" / "discounts.json"),
    )
    repository = InMemoryTraceRepository()
    orchestrator = AgentOrchestrator(
        responses_client=FailingResponsesClient(),
        dispatcher=ToolDispatcher(commerce),
        model="gpt-5.6-terra",
        reasoning_effort="low",
        max_output_tokens=2000,
    )
    service = ChatService(
        repository,
        orchestrator,
        RecommendationHydrator(commerce),
        PromotionPricingService(),
    )

    with pytest.raises(ChatServiceError) as captured:
        service.chat(ChatRequest(message="Trigger a provider failure"))

    assert captured.value.code == "openai_unavailable"
    trace = repository.get(captured.value.trace_id)
    assert trace is not None
    assert trace.model == "gpt-5.6-terra"
    assert trace.prompt_version == "phase7-v1"
    assert trace.tool_calls == []
    assert trace.token_usage.total_tokens == 0
    assert trace.errors[-1].code == "openai_unavailable"
    assert trace.errors[-1].message == "Model service is unavailable."
    serialized = json.dumps(trace.model_dump(mode="json"))
    assert "provider-secret" not in serialized
    assert "authorization" not in serialized.casefold()
    assert DEVELOPER_INSTRUCTIONS not in serialized


def test_chat_service_returns_valid_subset_and_separate_validation_evidence() -> None:
    model_client = ScriptedResponsesClient(
        [
            ModelResponse(
                response_id="resp-product",
                output_text="",
                function_calls=(
                    FunctionCall(
                        call_id="call-product",
                        name="get_product",
                        arguments_json='{"product_id":"JKT-003"}',
                    ),
                ),
                usage=ResponseUsage(),
                status="completed",
            ),
            ModelResponse(
                response_id="resp-final",
                output_text=final_output_json(
                    "The card facts are assembled by the application.",
                    ["jkt-003", "JKT-004", "UNKNOWN"],
                ),
                function_calls=(),
                usage=ResponseUsage(),
                status="completed",
            ),
        ]
    )
    service, repository = service_for(model_client)

    response = service.chat(ChatRequest(message="Find a jacket"))
    trace = repository.get(response.trace_id)

    assert [item.product_id for item in response.recommendations] == ["JKT-003"]
    assert response.recommendations[0].name == "Ridgeway Rain Shell"
    assert trace is not None
    assert trace.recommended_product_ids == ["JKT-003"]
    assert trace.recommendation_validation.all_products_exist is False
    assert trace.recommendation_validation.validation_errors == [
        "ungrounded_product_id:JKT-004",
        "unknown_product_id:UNKNOWN",
    ]
    assert trace.errors == []


def test_pricing_follows_first_accepted_recommendation_not_raw_or_search_order() -> (
    None
):
    model_client = ScriptedResponsesClient(
        [
            ModelResponse(
                response_id="resp-grounding",
                output_text="",
                function_calls=(
                    FunctionCall(
                        call_id="call-search",
                        name="search_products",
                        arguments_json='{"category":"jacket"}',
                    ),
                    FunctionCall(
                        call_id="call-discount",
                        name="validate_discount",
                        arguments_json='{"code":"welcome10"}',
                    ),
                ),
                usage=ResponseUsage(),
                status="completed",
            ),
            ModelResponse(
                response_id="resp-final",
                output_text=final_output_json(
                    "Two verified options.",
                    ["UNKNOWN", "JKT-003", "JKT-001"],
                    nominated_promotion_code=" welcome10 ",
                ),
                function_calls=(),
                usage=ResponseUsage(),
                status="completed",
            ),
        ]
    )
    service, repository = service_for(model_client)

    response = service.chat(ChatRequest(message="Use WELCOME10 on a jacket"))
    trace = repository.get(response.trace_id)

    assert [item.product_id for item in response.recommendations] == [
        "JKT-003",
        "JKT-001",
    ]
    assert response.recommendations[0].price == 110
    assert response.promotion is not None
    assert response.promotion.model_dump() == {
        "code": "WELCOME10",
        "valid": True,
        "discount_percent": 10,
        "reason": "active",
    }
    assert response.pricing is not None
    assert response.pricing.model_dump() == {
        "product_id": "JKT-003",
        "base_price": 110,
        "final_price": 99,
        "currency": "GBP",
        "discount_code": "WELCOME10",
        "discount_percent": 10,
    }
    assert trace is not None
    assert trace.recommended_product_ids == ["JKT-003", "JKT-001"]
    assert trace.recommendation_validation.validation_errors == [
        "unknown_product_id:UNKNOWN"
    ]
    assert trace.promotion == response.promotion
    assert trace.pricing == response.pricing
    assert trace.pricing.product_id == trace.recommended_product_ids[0]


@pytest.mark.parametrize(
    ("code", "valid", "reason"),
    [
        ("SUMMER20", False, "inactive"),
        ("STAFF99", False, "unknown_code"),
    ],
)
def test_invalid_promotion_is_authoritative_partial_result_without_pricing(
    code: str,
    valid: bool,
    reason: str,
) -> None:
    model_client = ScriptedResponsesClient(
        [
            ModelResponse(
                response_id="resp-discount",
                output_text="",
                function_calls=(
                    FunctionCall(
                        call_id="call-discount",
                        name="validate_discount",
                        arguments_json=json.dumps({"code": code}),
                    ),
                ),
                usage=ResponseUsage(),
                status="completed",
            ),
            ModelResponse(
                response_id="resp-final",
                output_text=final_output_json(
                    "The promotion was checked.",
                    nominated_promotion_code=code,
                ),
                function_calls=(),
                usage=ResponseUsage(),
                status="completed",
            ),
        ]
    )
    service, repository = service_for(model_client)

    response = service.chat(ChatRequest(message=f"Can I use {code}?"))
    trace = repository.get(response.trace_id)

    assert response.promotion is not None
    assert response.promotion.code == code
    assert response.promotion.valid is valid
    assert response.promotion.reason == reason
    assert response.promotion.discount_percent is None
    assert response.pricing is None
    assert trace is not None
    assert trace.promotion == response.promotion
    assert trace.pricing is None
    assert trace.errors == []


@pytest.mark.parametrize(
    ("nominated_code", "expected_error"),
    [
        (None, "promotion_nomination_missing"),
        ("STAFF99", "ungrounded_promotion_code"),
    ],
)
def test_promotion_nomination_failures_preserve_safe_http_result_and_trace_error(
    nominated_code: str | None,
    expected_error: str,
) -> None:
    model_client = ScriptedResponsesClient(
        [
            ModelResponse(
                response_id="resp-discount",
                output_text="",
                function_calls=(
                    FunctionCall(
                        call_id="call-discount",
                        name="validate_discount",
                        arguments_json='{"code":"WELCOME10"}',
                    ),
                ),
                usage=ResponseUsage(),
                status="completed",
            ),
            ModelResponse(
                response_id="resp-final",
                output_text=final_output_json(
                    "No grounded structured promotion is selected.",
                    nominated_promotion_code=nominated_code,
                ),
                function_calls=(),
                usage=ResponseUsage(),
                status="completed",
            ),
        ]
    )
    service, repository = service_for(model_client)

    response = service.chat(ChatRequest(message="Apply a promotion"))
    trace = repository.get(response.trace_id)

    assert response.promotion is None
    assert response.pricing is None
    assert trace is not None
    assert [error.code for error in trace.errors] == [expected_error]
    assert "WELCOME10" not in trace.errors[0].message
    assert "STAFF99" not in trace.errors[0].message


def test_pricing_calculation_failure_preserves_promotion_and_redacts_trace() -> None:
    model_client = ScriptedResponsesClient(
        [
            ModelResponse(
                response_id="resp-tools",
                output_text="",
                function_calls=(
                    FunctionCall(
                        call_id="call-product",
                        name="get_product",
                        arguments_json='{"product_id":"JKT-001"}',
                    ),
                    FunctionCall(
                        call_id="call-discount",
                        name="validate_discount",
                        arguments_json='{"code":"WELCOME10"}',
                    ),
                ),
                usage=ResponseUsage(),
                status="completed",
            ),
            ModelResponse(
                response_id="resp-final",
                output_text=final_output_json(
                    "A safe partial result remains available.",
                    ["JKT-001"],
                    nominated_promotion_code="WELCOME10",
                ),
                function_calls=(),
                usage=ResponseUsage(),
                status="completed",
            ),
        ]
    )
    service, repository = service_for(
        model_client,
        FailingPromotionPricingService(),
    )

    response = service.chat(ChatRequest(message="Apply the promotion"))
    trace = repository.get(response.trace_id)

    assert [item.product_id for item in response.recommendations] == ["JKT-001"]
    assert response.promotion is not None
    assert response.promotion.code == "WELCOME10"
    assert response.pricing is None
    assert trace is not None
    assert trace.promotion == response.promotion
    assert trace.pricing is None
    assert [error.model_dump() for error in trace.errors] == [
        {
            "code": "pricing_calculation_failed",
            "message": "Authoritative pricing could not be calculated safely.",
            "tool_call_id": None,
        }
    ]
    assert "exception" not in trace.model_dump_json().casefold()


def test_chat_service_maps_all_authoritative_product_availability_states() -> None:
    product_ids = ["JKT-003", "JKT-002", "JKT-001"]
    model_client = ScriptedResponsesClient(
        [
            ModelResponse(
                response_id="resp-products",
                output_text="",
                function_calls=tuple(
                    FunctionCall(
                        call_id=f"call-{product_id}",
                        name="get_product",
                        arguments_json=f'{{"product_id":"{product_id}"}}',
                    )
                    for product_id in product_ids
                ),
                usage=ResponseUsage(),
                status="completed",
            ),
            ModelResponse(
                response_id="resp-final",
                output_text=final_output_json("Three options.", product_ids),
                function_calls=(),
                usage=ResponseUsage(),
                status="completed",
            ),
        ]
    )
    service, repository = service_for(model_client)

    response = service.chat(ChatRequest(message="Show three jackets"))
    trace = repository.get(response.trace_id)

    assert [item.product_id for item in response.recommendations] == product_ids
    assert [item.availability for item in response.recommendations] == [
        "in_stock",
        "out_of_stock",
        "partial",
    ]
    assert trace is not None
    assert trace.recommended_product_ids == product_ids


def test_invalid_tool_evidence_persists_only_safe_terminal_trace() -> None:
    commerce = CommerceService(
        ProductRepository(ROOT / "data" / "products.json"),
        PromotionRepository(ROOT / "data" / "discounts.json"),
    )
    repository = InMemoryTraceRepository()
    model_client = ScriptedResponsesClient(
        [
            ModelResponse(
                response_id="resp-invalid-evidence",
                output_text="",
                function_calls=(
                    FunctionCall(
                        call_id="call-invalid-evidence",
                        name="get_product",
                        arguments_json='{"product_id":"JKT-003"}',
                    ),
                ),
                usage=ResponseUsage(total_tokens=2),
                status="completed",
            )
        ]
    )
    orchestrator = AgentOrchestrator(
        responses_client=model_client,
        dispatcher=InvalidEvidenceDispatcher(commerce),
        model="gpt-5.6-terra",
        reasoning_effort="low",
        max_output_tokens=2000,
    )
    service = ChatService(
        repository,
        orchestrator,
        RecommendationHydrator(commerce),
        PromotionPricingService(),
    )

    with pytest.raises(ChatServiceError) as captured:
        service.chat(ChatRequest(message="Trigger invalid evidence"))

    assert captured.value.code == "invalid_tool_evidence"
    trace = repository.get(captured.value.trace_id)
    assert trace is not None
    assert trace.tool_calls == []
    assert trace.recommended_product_ids == []
    assert trace.errors[-1].model_dump() == {
        "code": "invalid_tool_evidence",
        "message": "Tool result evidence could not be processed.",
        "tool_call_id": "call-invalid-evidence",
    }
    assert "raw secret" not in trace.model_dump_json()


def test_successful_turns_commit_merged_state_changes_and_bounded_history() -> None:
    model_client = ScriptedResponsesClient(
        [
            ModelResponse(
                response_id="resp-state-1",
                output_text=final_output_json(
                    "I will use that budget.",
                    constraint_updates=constraint_updates(
                        activity=TextUpdate(operation="set", value=" Hiking "),
                        maximum_price=MoneyTextUpdate(operation="set", value="160.00"),
                    ),
                ),
                function_calls=(),
                usage=ResponseUsage(),
                status="completed",
            ),
            ModelResponse(
                response_id="resp-state-2",
                output_text=final_output_json(
                    "I have updated the colour and budget.",
                    constraint_updates=constraint_updates(
                        maximum_price=MoneyTextUpdate(operation="set", value="120"),
                        colour=TextUpdate(operation="set", value=" Ocean   Blue "),
                    ),
                ),
                function_calls=(),
                usage=ResponseUsage(),
                status="completed",
            ),
        ]
    )
    service, traces, sessions = stateful_service_for(model_client)

    first = service.chat(ChatRequest(session_id="state-session", message="Under £160"))
    second = service.chat(
        ChatRequest(session_id="state-session", message="Actually £120 in blue")
    )
    first_trace = traces.get(first.trace_id)
    second_trace = traces.get(second.trace_id)
    state = sessions.get_state("state-session")

    assert first_trace is not None
    assert first_trace.resolved_constraints.activity == "Hiking"
    assert first_trace.resolved_constraints.maximum_price == 160
    assert [change.field for change in first_trace.constraint_changes] == [
        "activity",
        "maximum_price",
    ]
    assert second_trace is not None
    assert second_trace.turn_index == 2
    assert second_trace.resolved_constraints.activity == "Hiking"
    assert second_trace.resolved_constraints.maximum_price == 120
    assert second_trace.resolved_constraints.colour == "Ocean Blue"
    assert [change.field for change in second_trace.constraint_changes] == [
        "maximum_price",
        "colour",
    ]
    assert second_trace.constraint_changes[0].model_dump(mode="json") == {
        "field": "maximum_price",
        "previous": 160.0,
        "current": 120.0,
    }
    assert state.resolved_constraints.activity == "Hiking"
    assert state.resolved_constraints.maximum_price == 120
    assert state.resolved_constraints.colour == "Ocean Blue"
    assert [turn.user_message for turn in state.history] == [
        "Under £160",
        "Actually £120 in blue",
    ]


def test_failed_turn_preserves_state_and_history_but_consumes_turn_index() -> None:
    model_client = ScriptedResponsesClient(
        [
            ModelResponse(
                response_id="resp-success-1",
                output_text=final_output_json(
                    "Stored.",
                    constraint_updates=constraint_updates(
                        activity=TextUpdate(operation="set", value="Hiking")
                    ),
                ),
                function_calls=(),
                usage=ResponseUsage(),
                status="completed",
            ),
            ResponsesClientError("openai_unavailable"),
            ModelResponse(
                response_id="resp-success-3",
                output_text=final_output_json("Still hiking."),
                function_calls=(),
                usage=ResponseUsage(),
                status="completed",
            ),
        ]
    )
    service, traces, sessions = stateful_service_for(model_client)
    first = service.chat(ChatRequest(session_id="rollback", message="For hiking"))

    with pytest.raises(ChatServiceError) as captured:
        service.chat(ChatRequest(session_id="rollback", message="Failed request"))
    failure_trace = traces.get(captured.value.trace_id)
    after_failure = sessions.get_state("rollback")
    third = service.chat(ChatRequest(session_id="rollback", message="Continue"))
    third_trace = traces.get(third.trace_id)

    assert traces.get(first.trace_id) is not None
    assert failure_trace is not None
    assert failure_trace.turn_index == 2
    assert failure_trace.resolved_constraints.activity == "Hiking"
    assert failure_trace.constraint_changes == []
    assert [turn.user_message for turn in after_failure.history] == ["For hiking"]
    assert third_trace is not None
    assert third_trace.turn_index == 3
    assert "Failed request" not in [
        item.content for item in model_client.requests[-1].input
    ]


def test_history_stores_only_accepted_cards_and_evicts_after_six_successes() -> None:
    responses: list[ModelResponse] = []
    for index in range(7):
        responses.append(
            ModelResponse(
                response_id=f"resp-{index}",
                output_text=final_output_json(f"answer-{index}"),
                function_calls=(),
                usage=ResponseUsage(),
                status="completed",
            )
        )
    model_client = ScriptedResponsesClient(responses)
    service, _, sessions = stateful_service_for(model_client)

    for index in range(7):
        service.chat(ChatRequest(session_id="bounded", message=f"request-{index}"))

    state = sessions.get_state("bounded")
    assert [turn.user_message for turn in state.history] == [
        "request-1",
        "request-2",
        "request-3",
        "request-4",
        "request-5",
        "request-6",
    ]
    assert all(turn.recommended_product_ids == () for turn in state.history)


def test_same_session_chat_transactions_do_not_lose_concurrent_updates() -> None:
    first_entered_client = Event()
    release_first = Event()
    second_started = Event()
    second_entered_client = Event()

    class BlockingClient:
        def create_response(self, request: ResponseRequest) -> ModelResponse:
            current_message = request.input[-1].content
            if current_message == "Set activity":
                first_entered_client.set()
                assert release_first.wait(timeout=2)
                patch = constraint_updates(
                    activity=TextUpdate(operation="set", value="Hiking")
                )
                response_id = "first"
            else:
                second_entered_client.set()
                patch = constraint_updates(
                    colour=TextUpdate(operation="set", value="Blue")
                )
                response_id = "second"
            return ModelResponse(
                response_id=response_id,
                output_text=final_output_json("Done", constraint_updates=patch),
                function_calls=(),
                usage=ResponseUsage(),
                status="completed",
            )

    commerce = CommerceService(
        ProductRepository(ROOT / "data" / "products.json"),
        PromotionRepository(ROOT / "data" / "discounts.json"),
    )
    sessions = InMemorySessionRepository()
    service = ChatService(
        InMemoryTraceRepository(),
        AgentOrchestrator(
            responses_client=BlockingClient(),
            dispatcher=ToolDispatcher(commerce),
            model="gpt-5.6-terra",
            reasoning_effort="low",
            max_output_tokens=2000,
        ),
        RecommendationHydrator(commerce),
        PromotionPricingService(),
        sessions,
    )

    def second_turn() -> None:
        second_started.set()
        service.chat(ChatRequest(session_id="shared", message="Set colour"))

    with ThreadPoolExecutor(max_workers=2) as executor:
        first = executor.submit(
            service.chat,
            ChatRequest(session_id="shared", message="Set activity"),
        )
        assert first_entered_client.wait(timeout=2)
        second = executor.submit(second_turn)
        assert second_started.wait(timeout=2)
        assert not second_entered_client.is_set()
        release_first.set()
        first.result(timeout=2)
        second.result(timeout=2)

    state = sessions.get_state("shared")
    assert state.resolved_constraints.activity == "Hiking"
    assert state.resolved_constraints.colour == "Blue"
    assert [turn.user_message for turn in state.history] == [
        "Set activity",
        "Set colour",
    ]


def test_historical_cards_need_fresh_current_turn_grounding_in_followups() -> None:
    model_client = ScriptedResponsesClient(
        [
            ModelResponse(
                response_id="turn-1-tool",
                output_text="",
                function_calls=(
                    FunctionCall(
                        call_id="turn-1-get",
                        name="get_product",
                        arguments_json='{"product_id":"JKT-001"}',
                    ),
                ),
                usage=ResponseUsage(),
                status="completed",
            ),
            ModelResponse(
                response_id="turn-1-final",
                output_text=final_output_json("First card.", ["JKT-001"]),
                function_calls=(),
                usage=ResponseUsage(),
                status="completed",
            ),
            ModelResponse(
                response_id="turn-2-final",
                output_text=final_output_json(
                    "I can discuss the prior card.", ["JKT-001"]
                ),
                function_calls=(),
                usage=ResponseUsage(),
                status="completed",
            ),
            ModelResponse(
                response_id="turn-3-tool",
                output_text="",
                function_calls=(
                    FunctionCall(
                        call_id="turn-3-get",
                        name="get_product",
                        arguments_json='{"product_id":"JKT-001"}',
                    ),
                ),
                usage=ResponseUsage(),
                status="completed",
            ),
            ModelResponse(
                response_id="turn-3-final",
                output_text=final_output_json("Fresh card.", ["JKT-001"]),
                function_calls=(),
                usage=ResponseUsage(),
                status="completed",
            ),
        ]
    )
    service, traces, sessions = stateful_service_for(model_client)

    first = service.chat(ChatRequest(session_id="followup", message="Show JKT-001"))
    second = service.chat(ChatRequest(session_id="followup", message="What about it?"))
    third = service.chat(
        ChatRequest(session_id="followup", message="Show the card again")
    )
    second_trace = traces.get(second.trace_id)

    assert [item.product_id for item in first.recommendations] == ["JKT-001"]
    assert second.recommendations == []
    assert second_trace is not None
    assert second_trace.recommendation_validation.validation_errors == [
        "ungrounded_product_id:JKT-001"
    ]
    assert [item.product_id for item in third.recommendations] == ["JKT-001"]
    assert model_client.requests[2].previous_response_id is None
    historical_assistant = model_client.requests[2].input[1]
    assert '"recommended_product_ids":["JKT-001"]' in historical_assistant.content
    assert sessions.get_state("followup").history[1].recommended_product_ids == ()


def test_followup_pricing_requires_fresh_product_and_promotion_evidence() -> None:
    model_client = ScriptedResponsesClient(
        [
            ModelResponse(
                response_id="turn-1-tool",
                output_text="",
                function_calls=(
                    FunctionCall(
                        call_id="turn-1-get",
                        name="get_product",
                        arguments_json='{"product_id":"JKT-001"}',
                    ),
                ),
                usage=ResponseUsage(),
                status="completed",
            ),
            ModelResponse(
                response_id="turn-1-final",
                output_text=final_output_json("First card.", ["JKT-001"]),
                function_calls=(),
                usage=ResponseUsage(),
                status="completed",
            ),
            ModelResponse(
                response_id="turn-2-tools",
                output_text="",
                function_calls=(
                    FunctionCall(
                        call_id="turn-2-get",
                        name="get_product",
                        arguments_json='{"product_id":"JKT-001"}',
                    ),
                    FunctionCall(
                        call_id="turn-2-discount",
                        name="validate_discount",
                        arguments_json='{"code":"WELCOME10"}',
                    ),
                ),
                usage=ResponseUsage(),
                status="completed",
            ),
            ModelResponse(
                response_id="turn-2-final",
                output_text=final_output_json(
                    "WELCOME10 was freshly checked for the refreshed card.",
                    ["JKT-001"],
                    nominated_promotion_code="WELCOME10",
                ),
                function_calls=(),
                usage=ResponseUsage(),
                status="completed",
            ),
            ModelResponse(
                response_id="turn-3-tool",
                output_text="",
                function_calls=(
                    FunctionCall(
                        call_id="turn-3-get",
                        name="get_product",
                        arguments_json='{"product_id":"JKT-001"}',
                    ),
                ),
                usage=ResponseUsage(),
                status="completed",
            ),
            ModelResponse(
                response_id="turn-3-final",
                output_text=final_output_json(
                    "The prior code is only historical context.",
                    ["JKT-001"],
                    nominated_promotion_code="WELCOME10",
                ),
                function_calls=(),
                usage=ResponseUsage(),
                status="completed",
            ),
            ModelResponse(
                response_id="turn-4-tool",
                output_text="",
                function_calls=(
                    FunctionCall(
                        call_id="turn-4-discount",
                        name="validate_discount",
                        arguments_json='{"code":"WELCOME10"}',
                    ),
                ),
                usage=ResponseUsage(),
                status="completed",
            ),
            ModelResponse(
                response_id="turn-4-final",
                output_text=final_output_json(
                    "The product still needs a current-turn refresh.",
                    ["JKT-001"],
                    nominated_promotion_code="WELCOME10",
                ),
                function_calls=(),
                usage=ResponseUsage(),
                status="completed",
            ),
        ]
    )
    service, traces, _ = stateful_service_for(model_client)

    first = service.chat(ChatRequest(session_id="priced-followup", message="Show it"))
    second = service.chat(
        ChatRequest(session_id="priced-followup", message="Apply WELCOME10")
    )
    third = service.chat(
        ChatRequest(session_id="priced-followup", message="Use that code again")
    )
    fourth = service.chat(
        ChatRequest(session_id="priced-followup", message="Validate the code only")
    )
    third_trace = traces.get(third.trace_id)
    fourth_trace = traces.get(fourth.trace_id)

    assert first.pricing is None
    assert second.promotion is not None
    assert second.pricing is not None
    assert second.pricing.product_id == "JKT-001"
    assert second.pricing.final_price == 130.5
    assert [item.product_id for item in third.recommendations] == ["JKT-001"]
    assert third.promotion is None
    assert third.pricing is None
    assert third_trace is not None
    assert [error.code for error in third_trace.errors] == ["ungrounded_promotion_code"]
    assert fourth.recommendations == []
    assert fourth.promotion is not None
    assert fourth.promotion.valid is True
    assert fourth.pricing is None
    assert fourth_trace is not None
    assert fourth_trace.recommendation_validation.validation_errors == [
        "ungrounded_product_id:JKT-001"
    ]
    initial_request_ids = [
        model_client.requests[index].previous_response_id for index in (0, 2, 4, 6)
    ]
    assert initial_request_ids == [
        None,
        None,
        None,
        None,
    ]
