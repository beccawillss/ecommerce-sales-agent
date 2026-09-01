"""Tests for chat response assembly and safe trace persistence."""

import json
from collections.abc import Mapping
from pathlib import Path

import pytest

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
from salesagent.repositories.products import ProductRepository
from salesagent.repositories.promotions import PromotionRepository
from salesagent.repositories.traces import InMemoryTraceRepository
from salesagent.services.chat import ChatService, ChatServiceError
from salesagent.services.commerce import CommerceService
from salesagent.services.recommendations import RecommendationHydrator
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


def service_for(
    model_client: ScriptedResponsesClient,
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
        ChatService(repository, orchestrator, RecommendationHydrator(commerce)),
        repository,
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
    service = ChatService(repository, orchestrator, RecommendationHydrator(commerce))

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
    assert trace.prompt_version == "phase5-v1"
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
    service = ChatService(repository, orchestrator, RecommendationHydrator(commerce))

    with pytest.raises(ChatServiceError) as captured:
        service.chat(ChatRequest(message="Trigger a provider failure"))

    assert captured.value.code == "openai_unavailable"
    trace = repository.get(captured.value.trace_id)
    assert trace is not None
    assert trace.model == "gpt-5.6-terra"
    assert trace.prompt_version == "phase5-v1"
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
    service = ChatService(repository, orchestrator, RecommendationHydrator(commerce))

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
