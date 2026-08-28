"""Tests for chat response assembly and safe trace persistence."""

import json
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
from salesagent.api.models import ChatRequest
from salesagent.repositories.products import ProductRepository
from salesagent.repositories.promotions import PromotionRepository
from salesagent.repositories.traces import InMemoryTraceRepository
from salesagent.services.chat import ChatService, ChatServiceError
from salesagent.services.commerce import CommerceService
from tests.fakes import ScriptedResponsesClient

ROOT = Path(__file__).resolve().parents[1]


class FailingResponsesClient:
    """Raise a safe adapter error chained from recognizable provider text."""

    def create_response(self, request: ResponseRequest) -> ModelResponse:
        try:
            raise RuntimeError("provider-secret-and-authorization-header")
        except RuntimeError as error:
            raise ResponsesClientError("openai_unavailable") from error


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
                output_text="The verified jacket costs £145.",
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
    service = ChatService(repository, orchestrator)

    response = service.chat(
        ChatRequest(session_id="session-trace", message="Tell me about JKT-001")
    )
    trace = repository.get(response.trace_id)

    assert response.message == "The verified jacket costs £145."
    assert response.recommendations == []
    assert response.promotion is None
    assert response.pricing is None
    assert trace is not None
    assert trace.session_id == "session-trace"
    assert trace.turn_index == 1
    assert trace.model == "gpt-5.6-terra"
    assert trace.prompt_version == "phase4-v1"
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
    service = ChatService(repository, orchestrator)

    with pytest.raises(ChatServiceError) as captured:
        service.chat(ChatRequest(message="Trigger a provider failure"))

    assert captured.value.code == "openai_unavailable"
    trace = repository.get(captured.value.trace_id)
    assert trace is not None
    assert trace.model == "gpt-5.6-terra"
    assert trace.prompt_version == "phase4-v1"
    assert trace.tool_calls == []
    assert trace.token_usage.total_tokens == 0
    assert trace.errors[-1].code == "openai_unavailable"
    assert trace.errors[-1].message == "Model service is unavailable."
    serialized = json.dumps(trace.model_dump(mode="json"))
    assert "provider-secret" not in serialized
    assert "authorization" not in serialized.casefold()
    assert DEVELOPER_INSTRUCTIONS not in serialized
