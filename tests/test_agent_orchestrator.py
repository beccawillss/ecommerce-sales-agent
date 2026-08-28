"""Offline behavior tests for the one-turn Responses orchestrator."""

from collections.abc import Mapping
from pathlib import Path

import pytest

from salesagent.agent.instructions import DEVELOPER_INSTRUCTIONS, PROMPT_VERSION
from salesagent.agent.orchestrator import AgentOrchestrationError, AgentOrchestrator
from salesagent.agent.responses_client import (
    FunctionCall,
    FunctionCallOutput,
    ModelResponse,
    ResponsesClient,
    ResponseUsage,
)
from salesagent.agent.tools.dispatcher import ToolDispatcher
from salesagent.agent.tools.models import ToolExecutionResult
from salesagent.repositories.products import ProductRepository
from salesagent.repositories.promotions import PromotionRepository
from salesagent.services.commerce import CommerceService
from tests.fakes import ScriptedResponsesClient

ROOT = Path(__file__).resolve().parents[1]


class NoCallDispatcher(ToolDispatcher):
    """Record every dispatch while retaining the real Phase 3 boundary."""

    def __init__(self, commerce: CommerceService) -> None:
        super().__init__(commerce)
        self.calls: list[tuple[str, dict[str, object]]] = []

    def dispatch(
        self, tool_name: str, arguments: Mapping[str, object]
    ) -> ToolExecutionResult:
        copied = dict(arguments)
        self.calls.append((tool_name, copied))
        return super().dispatch(tool_name, copied)


@pytest.fixture
def dispatcher() -> NoCallDispatcher:
    commerce = CommerceService(
        ProductRepository(ROOT / "data" / "products.json"),
        PromotionRepository(ROOT / "data" / "discounts.json"),
    )
    return NoCallDispatcher(commerce)


def orchestrator(
    client: ResponsesClient, dispatcher: ToolDispatcher
) -> AgentOrchestrator:
    return AgentOrchestrator(
        responses_client=client,
        dispatcher=dispatcher,
        model="gpt-5.6-terra",
        reasoning_effort="low",
        max_output_tokens=2000,
    )


def test_direct_final_response_preserves_text_configuration_and_usage(
    dispatcher: ToolDispatcher,
) -> None:
    usage = ResponseUsage(input_tokens=12, output_tokens=8, total_tokens=20)
    client = ScriptedResponsesClient(
        [
            ModelResponse(
                response_id="resp-direct",
                output_text="  What activity are you shopping for?  ",
                function_calls=(),
                usage=usage,
                status="completed",
            )
        ]
    )

    result = orchestrator(client, dispatcher).run("I need a jacket")

    assert result.final_text == "What activity are you shopping for?"
    assert result.model == "gpt-5.6-terra"
    assert result.prompt_version == PROMPT_VERSION
    assert result.usage == usage
    assert len(client.requests) == 1
    request = client.requests[0]
    assert request.input == "I need a jacket"
    assert request.previous_response_id is None
    assert request.instructions == DEVELOPER_INSTRUCTIONS
    assert request.reasoning_effort == "low"
    assert request.max_output_tokens == 2000
    assert [tool["name"] for tool in request.tools] == [
        "search_products",
        "get_product",
        "check_inventory",
        "validate_discount",
    ]


@pytest.mark.parametrize(
    "response",
    [
        ModelResponse(
            response_id="resp-empty",
            output_text="   ",
            function_calls=(),
            usage=ResponseUsage(total_tokens=3),
            status="completed",
        ),
        ModelResponse(
            response_id="resp-incomplete",
            output_text="partial",
            function_calls=(),
            usage=ResponseUsage(total_tokens=4),
            status="incomplete",
            incomplete_reason="max_output_tokens",
        ),
        ModelResponse(
            response_id=None,
            output_text="text",
            function_calls=(),
            usage=ResponseUsage(total_tokens=5),
            status="completed",
        ),
    ],
)
def test_unusable_direct_response_fails_safely(
    dispatcher: ToolDispatcher, response: ModelResponse
) -> None:
    client = ScriptedResponsesClient([response])

    with pytest.raises(AgentOrchestrationError) as captured:
        orchestrator(client, dispatcher).run("Hello")

    assert captured.value.code == "malformed_model_response"
    assert captured.value.usage == response.usage
    assert len(client.requests) == 1


def test_one_tool_call_round_trips_exact_id_and_continues_to_final_text(
    dispatcher: NoCallDispatcher,
) -> None:
    client = ScriptedResponsesClient(
        [
            ModelResponse(
                response_id="resp-tools",
                output_text="ignored partial prose",
                function_calls=(
                    FunctionCall(
                        call_id="call-exact-123",
                        name="validate_discount",
                        arguments_json='{"code":"UNKNOWN"}',
                    ),
                ),
                usage=ResponseUsage(input_tokens=5, output_tokens=3, total_tokens=8),
                status="completed",
            ),
            ModelResponse(
                response_id="resp-final",
                output_text="That promotion code is not recognized.",
                function_calls=(),
                usage=ResponseUsage(input_tokens=7, output_tokens=4, total_tokens=11),
                status="completed",
            ),
        ]
    )

    result = orchestrator(client, dispatcher).run("Can I use UNKNOWN?")

    assert result.final_text == "That promotion code is not recognized."
    assert result.usage == ResponseUsage(
        input_tokens=12,
        output_tokens=7,
        total_tokens=19,
    )
    assert result.tool_calls[0].call_id == "call-exact-123"
    assert result.tool_calls[0].tool_name == "validate_discount"
    assert result.tool_calls[0].arguments == {"code": "UNKNOWN"}
    assert result.tool_calls[0].result["success"] is True
    assert result.tool_calls[0].status == "success"
    assert result.errors == ()
    assert dispatcher.calls == [("validate_discount", {"code": "UNKNOWN"})]
    continuation = client.requests[1]
    assert continuation.previous_response_id == "resp-tools"
    assert continuation.instructions == DEVELOPER_INSTRUCTIONS
    assert isinstance(continuation.input, tuple)
    assert continuation.input[0].call_id == "call-exact-123"
    output = continuation.input[0].output
    assert '"success":true' in output
    assert '"valid":false' in output


def test_sequential_responses_chain_to_immediately_preceding_id(
    dispatcher: NoCallDispatcher,
) -> None:
    client = ScriptedResponsesClient(
        [
            ModelResponse(
                response_id="resp-search",
                output_text="",
                function_calls=(
                    FunctionCall(
                        call_id="call-search",
                        name="search_products",
                        arguments_json='{"activity":"cycling"}',
                    ),
                ),
                usage=ResponseUsage(total_tokens=1),
                status="completed",
            ),
            ModelResponse(
                response_id="resp-stock",
                output_text="",
                function_calls=(
                    FunctionCall(
                        call_id="call-stock",
                        name="check_inventory",
                        arguments_json=(
                            '{"product_id":"JKT-001","colour":"Ocean Blue","size":"M"}'
                        ),
                    ),
                ),
                usage=ResponseUsage(total_tokens=2),
                status="completed",
            ),
            ModelResponse(
                response_id="resp-final",
                output_text="The Ocean Blue size M is in stock.",
                function_calls=(),
                usage=ResponseUsage(total_tokens=3),
                status="completed",
            ),
        ]
    )

    result = orchestrator(client, dispatcher).run("Find cycling stock")

    assert result.usage.total_tokens == 6
    assert [call[0] for call in dispatcher.calls] == [
        "search_products",
        "check_inventory",
    ]
    assert [request.previous_response_id for request in client.requests] == [
        None,
        "resp-search",
        "resp-stock",
    ]


def test_multiple_calls_in_one_response_dispatch_and_return_in_order(
    dispatcher: NoCallDispatcher,
) -> None:
    client = ScriptedResponsesClient(
        [
            ModelResponse(
                response_id="resp-batch",
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
                output_text="Here are the verified details.",
                function_calls=(),
                usage=ResponseUsage(),
                status="completed",
            ),
        ]
    )

    orchestrator(client, dispatcher).run("Check both")

    assert [call[0] for call in dispatcher.calls] == [
        "get_product",
        "validate_discount",
    ]
    output_items = client.requests[1].input
    assert isinstance(output_items, tuple)
    assert [item.call_id for item in output_items] == [
        "call-product",
        "call-discount",
    ]


@pytest.mark.parametrize("arguments_json", ["{broken", "[]", "null", '"text"'])
def test_malformed_or_non_object_arguments_are_recoverable(
    dispatcher: NoCallDispatcher, arguments_json: str
) -> None:
    client = ScriptedResponsesClient(
        [
            ModelResponse(
                response_id="resp-invalid",
                output_text="",
                function_calls=(
                    FunctionCall(
                        call_id="call-invalid",
                        name="get_product",
                        arguments_json=arguments_json,
                    ),
                ),
                usage=ResponseUsage(),
                status="completed",
            ),
            ModelResponse(
                response_id="resp-recovered",
                output_text="Which product did you mean?",
                function_calls=(),
                usage=ResponseUsage(),
                status="completed",
            ),
        ]
    )

    result = orchestrator(client, dispatcher).run("Tell me about it")

    assert result.final_text == "Which product did you mean?"
    assert dispatcher.calls == []
    assert result.tool_calls == ()
    assert result.errors[0].code == "invalid_arguments"
    assert result.errors[0].tool_call_id == "call-invalid"
    output_items = client.requests[1].input
    assert isinstance(output_items, tuple)
    assert output_items == (
        FunctionCallOutput(
            call_id="call-invalid",
            output=(
                '{"arguments":null,"data":null,"duration_ms":0,'
                '"error":{"code":"invalid_arguments","message":'
                '"Arguments must be one valid JSON object."},"success":false,'
                '"tool_name":"get_product"}'
            ),
        ),
    )


@pytest.mark.parametrize("call_id", [None, "", "   "])
def test_missing_call_id_is_terminal_before_dispatch(
    dispatcher: NoCallDispatcher, call_id: str | None
) -> None:
    client = ScriptedResponsesClient(
        [
            ModelResponse(
                response_id="resp-bad-id",
                output_text="",
                function_calls=(
                    FunctionCall(
                        call_id=call_id,
                        name="get_product",
                        arguments_json='{"product_id":"JKT-001"}',
                    ),
                ),
                usage=ResponseUsage(total_tokens=2),
                status="completed",
            )
        ]
    )

    with pytest.raises(AgentOrchestrationError) as captured:
        orchestrator(client, dispatcher).run("Tell me about it")

    assert captured.value.code == "malformed_model_response"
    assert dispatcher.calls == []
    assert len(client.requests) == 1


def test_duplicate_call_ids_in_batch_dispatch_nothing(
    dispatcher: NoCallDispatcher,
) -> None:
    duplicate_calls = tuple(
        FunctionCall(
            call_id="call-duplicate",
            name="get_product",
            arguments_json='{"product_id":"JKT-001"}',
        )
        for _ in range(2)
    )
    client = ScriptedResponsesClient(
        [
            ModelResponse(
                response_id="resp-duplicate",
                output_text="",
                function_calls=duplicate_calls,
                usage=ResponseUsage(),
                status="completed",
            )
        ]
    )

    with pytest.raises(AgentOrchestrationError) as captured:
        orchestrator(client, dispatcher).run("Tell me about it")

    assert captured.value.code == "malformed_model_response"
    assert dispatcher.calls == []
    assert len(client.requests) == 1


def test_reused_call_id_across_responses_is_terminal_without_new_dispatch(
    dispatcher: NoCallDispatcher,
) -> None:
    repeated_call = FunctionCall(
        call_id="call-reused",
        name="get_product",
        arguments_json='{"product_id":"JKT-001"}',
    )
    client = ScriptedResponsesClient(
        [
            ModelResponse(
                response_id="resp-one",
                output_text="",
                function_calls=(repeated_call,),
                usage=ResponseUsage(),
                status="completed",
            ),
            ModelResponse(
                response_id="resp-two",
                output_text="",
                function_calls=(repeated_call,),
                usage=ResponseUsage(),
                status="completed",
            ),
        ]
    )

    with pytest.raises(AgentOrchestrationError) as captured:
        orchestrator(client, dispatcher).run("Tell me about it")

    assert captured.value.code == "malformed_model_response"
    assert len(dispatcher.calls) == 1
    assert len(captured.value.tool_calls) == 1
    assert len(client.requests) == 2


@pytest.mark.parametrize(
    ("name", "arguments_json", "error_code"),
    [
        ("get_product", "{}", "invalid_arguments"),
        ("delete_inventory", "{}", "unknown_tool"),
    ],
)
def test_dispatcher_rejections_return_safe_output_and_allow_recovery(
    dispatcher: NoCallDispatcher,
    name: str,
    arguments_json: str,
    error_code: str,
) -> None:
    client = ScriptedResponsesClient(
        [
            ModelResponse(
                response_id="resp-rejected",
                output_text="",
                function_calls=(
                    FunctionCall(
                        call_id="call-rejected",
                        name=name,
                        arguments_json=arguments_json,
                    ),
                ),
                usage=ResponseUsage(),
                status="completed",
            ),
            ModelResponse(
                response_id="resp-final",
                output_text="I could not verify that request.",
                function_calls=(),
                usage=ResponseUsage(),
                status="completed",
            ),
        ]
    )

    result = orchestrator(client, dispatcher).run("Try this")

    assert result.final_text == "I could not verify that request."
    assert result.tool_calls == ()
    assert result.errors[0].code == error_code
    assert result.errors[0].tool_call_id == "call-rejected"
    continuation = client.requests[1].input
    assert isinstance(continuation, tuple)
    assert f'"code":"{error_code}"' in continuation[0].output
    assert continuation[0].call_id == "call-rejected"


def test_product_not_found_is_traced_tool_error_and_can_recover(
    dispatcher: NoCallDispatcher,
) -> None:
    client = ScriptedResponsesClient(
        [
            ModelResponse(
                response_id="resp-missing-product",
                output_text="",
                function_calls=(
                    FunctionCall(
                        call_id="call-missing-product",
                        name="get_product",
                        arguments_json='{"product_id":"UNKNOWN"}',
                    ),
                ),
                usage=ResponseUsage(),
                status="completed",
            ),
            ModelResponse(
                response_id="resp-final",
                output_text="I could not find that product.",
                function_calls=(),
                usage=ResponseUsage(),
                status="completed",
            ),
        ]
    )

    result = orchestrator(client, dispatcher).run("Find UNKNOWN")

    assert result.tool_calls[0].status == "error"
    assert result.tool_calls[0].result["error"]["code"] == "product_not_found"
    assert result.errors == ()


def test_third_identical_call_is_terminal_and_is_not_dispatched(
    dispatcher: NoCallDispatcher,
) -> None:
    equivalent_arguments = [
        '{"product_id":"JKT-001","colour":"Ocean Blue","size":"M"}',
        '{"size":"M","product_id":"JKT-001","colour":"Ocean Blue"}',
        '{"colour":"Ocean Blue","size":"M","product_id":"JKT-001"}',
    ]
    responses = [
        ModelResponse(
            response_id=f"resp-{index}",
            output_text="",
            function_calls=(
                FunctionCall(
                    call_id=f"call-{index}",
                    name="check_inventory",
                    arguments_json=arguments_json,
                ),
            ),
            usage=ResponseUsage(total_tokens=1),
            status="completed",
        )
        for index, arguments_json in enumerate(equivalent_arguments, start=1)
    ]
    client = ScriptedResponsesClient(responses)

    with pytest.raises(AgentOrchestrationError) as captured:
        orchestrator(client, dispatcher).run("Keep checking")

    assert captured.value.code == "orchestration_limit_reached"
    assert captured.value.tool_call_id == "call-3"
    assert len(dispatcher.calls) == 2
    assert len(client.requests) == 3


def test_more_than_eight_returned_calls_fails_before_dispatch(
    dispatcher: NoCallDispatcher,
) -> None:
    calls = tuple(
        FunctionCall(
            call_id=f"call-{index}",
            name="get_product",
            arguments_json=f'{{"product_id":"JKT-{index:03d}"}}',
        )
        for index in range(9)
    )
    client = ScriptedResponsesClient(
        [
            ModelResponse(
                response_id="resp-too-many",
                output_text="",
                function_calls=calls,
                usage=ResponseUsage(),
                status="completed",
            )
        ]
    )

    with pytest.raises(AgentOrchestrationError) as captured:
        orchestrator(client, dispatcher).run("Check many")

    assert captured.value.code == "orchestration_limit_reached"
    assert dispatcher.calls == []
    assert len(client.requests) == 1


def test_six_responses_without_final_text_reaches_response_limit(
    dispatcher: NoCallDispatcher,
) -> None:
    client = ScriptedResponsesClient(
        [
            ModelResponse(
                response_id=f"resp-{index}",
                output_text="",
                function_calls=(
                    FunctionCall(
                        call_id=f"call-{index}",
                        name="get_product",
                        arguments_json=f'{{"product_id":"JKT-{index:03d}"}}',
                    ),
                ),
                usage=ResponseUsage(total_tokens=index),
                status="completed",
            )
            for index in range(1, 7)
        ]
    )

    with pytest.raises(AgentOrchestrationError) as captured:
        orchestrator(client, dispatcher).run("Never finish")

    assert captured.value.code == "orchestration_limit_reached"
    assert captured.value.usage.total_tokens == 21
    assert len(client.requests) == 6
    assert len(dispatcher.calls) == 6
