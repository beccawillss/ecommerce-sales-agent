"""Offline mapping tests for the concrete OpenAI Responses adapter."""

from types import SimpleNamespace
from typing import Any

import httpx2
import openai
import pytest

from salesagent.agent.final_output import final_output_text_format
from salesagent.agent.responses_client import (
    FunctionCallOutput,
    OpenAIResponsesClient,
    ResponseRequest,
    ResponsesClientError,
)


class FakeResponsesResource:
    def __init__(self, response: object | Exception) -> None:
        self.response = response
        self.calls: list[dict[str, Any]] = []

    def create(self, **kwargs: Any) -> object:
        self.calls.append(kwargs)
        if isinstance(self.response, Exception):
            raise self.response
        return self.response


def request(
    input_value: str | tuple[FunctionCallOutput, ...] = "Find a jacket",
    *,
    previous_response_id: str | None = None,
) -> ResponseRequest:
    return ResponseRequest(
        input=input_value,
        previous_response_id=previous_response_id,
        model="gpt-5.6-terra",
        instructions="developer instructions",
        tools=({"type": "function", "name": "search_products"},),
        text_format=final_output_text_format(),
        reasoning_effort="low",
        max_output_tokens=2000,
    )


def test_adapter_maps_text_calls_order_usage_and_configuration() -> None:
    response = SimpleNamespace(
        id="resp-1",
        output_text="I found options.",
        status="completed",
        incomplete_details=None,
        output=[
            SimpleNamespace(
                type="function_call",
                call_id="call-1",
                name="search_products",
                arguments='{"category":"jacket"}',
            ),
            SimpleNamespace(type="reasoning", encrypted_content="must-not-survive"),
            SimpleNamespace(
                type="function_call",
                call_id="call-2",
                name="check_inventory",
                arguments='{"product_id":"JKT-001"}',
            ),
        ],
        usage=SimpleNamespace(input_tokens=11, output_tokens=7, total_tokens=18),
    )
    resource = FakeResponsesResource(response)
    client = OpenAIResponsesClient(
        api_key="test-key",
        timeout_seconds=30,
        sdk_client=SimpleNamespace(responses=resource),
    )

    snapshot = client.create_response(request())

    assert snapshot.response_id == "resp-1"
    assert snapshot.output_text == "I found options."
    assert snapshot.status == "completed"
    assert [call.call_id for call in snapshot.function_calls] == ["call-1", "call-2"]
    assert snapshot.usage.input_tokens == 11
    assert snapshot.usage.output_tokens == 7
    assert snapshot.usage.total_tokens == 18
    assert not hasattr(snapshot, "reasoning")
    assert resource.calls == [
        {
            "model": "gpt-5.6-terra",
            "input": "Find a jacket",
            "previous_response_id": None,
            "instructions": "developer instructions",
            "tools": [{"type": "function", "name": "search_products"}],
            "text": {"format": final_output_text_format()},
            "reasoning": {"effort": "low"},
            "max_output_tokens": 2000,
            "tool_choice": "auto",
            "parallel_tool_calls": False,
            "store": True,
        }
    ]


def test_adapter_maps_correlated_function_outputs_for_continuation() -> None:
    response = SimpleNamespace(
        id="resp-2",
        output_text="Done",
        output=[],
        usage=None,
        status="completed",
        incomplete_details=None,
    )
    resource = FakeResponsesResource(response)
    client = OpenAIResponsesClient(
        api_key="test-key",
        timeout_seconds=30,
        sdk_client=SimpleNamespace(responses=resource),
    )

    client.create_response(
        request(
            (FunctionCallOutput(call_id="call-exact", output='{"success":true}'),),
            previous_response_id="resp-1",
        )
    )

    assert resource.calls[0]["input"] == [
        {
            "type": "function_call_output",
            "call_id": "call-exact",
            "output": '{"success":true}',
        }
    ]
    assert resource.calls[0]["previous_response_id"] == "resp-1"
    assert resource.calls[0]["instructions"] == "developer instructions"
    assert resource.calls[0]["text"] == {"format": final_output_text_format()}


def test_adapter_preserves_incomplete_status_reason_and_missing_call_id() -> None:
    response = SimpleNamespace(
        id="resp-incomplete",
        output_text=None,
        output=[
            SimpleNamespace(
                type="function_call",
                name="get_product",
                arguments='{"product_id":"JKT-001"}',
            )
        ],
        usage=SimpleNamespace(input_tokens=2, output_tokens=3, total_tokens=5),
        status="incomplete",
        incomplete_details=SimpleNamespace(reason="max_output_tokens"),
    )
    resource = FakeResponsesResource(response)
    client = OpenAIResponsesClient(
        api_key="test-key",
        timeout_seconds=30,
        sdk_client=SimpleNamespace(responses=resource),
    )

    snapshot = client.create_response(request())

    assert snapshot.status == "incomplete"
    assert snapshot.incomplete_reason == "max_output_tokens"
    assert snapshot.output_text == ""
    assert snapshot.function_calls[0].call_id is None


def test_adapter_rejects_invalid_usage_metadata_safely() -> None:
    response = SimpleNamespace(
        id="resp-bad-usage",
        output_text="text",
        output=[],
        usage=SimpleNamespace(input_tokens=-1, output_tokens=3, total_tokens=2),
        status="completed",
        incomplete_details=None,
    )
    resource = FakeResponsesResource(response)
    client = OpenAIResponsesClient(
        api_key="test-key",
        timeout_seconds=30,
        sdk_client=SimpleNamespace(responses=resource),
    )

    with pytest.raises(ResponsesClientError) as captured:
        client.create_response(request())

    assert captured.value.code == "malformed_model_response"


def test_adapter_is_lazy_and_missing_key_is_a_safe_error() -> None:
    constructed = False

    def factory(**_: object) -> object:
        nonlocal constructed
        constructed = True
        return object()

    client = OpenAIResponsesClient(
        api_key=None,
        timeout_seconds=30,
        client_factory=factory,
    )

    assert constructed is False
    with pytest.raises(ResponsesClientError) as captured:
        client.create_response(request())
    assert captured.value.code == "missing_openai_configuration"
    assert constructed is False


def test_adapter_constructs_official_client_only_on_first_call() -> None:
    response = SimpleNamespace(
        id="resp-1",
        output_text="Hello",
        output=[],
        usage=None,
        status="completed",
        incomplete_details=None,
    )
    resource = FakeResponsesResource(response)
    calls: list[dict[str, object]] = []

    def factory(**kwargs: object) -> object:
        calls.append(kwargs)
        return SimpleNamespace(responses=resource)

    client = OpenAIResponsesClient(
        api_key="test-key",
        timeout_seconds=12.5,
        max_retries=2,
        client_factory=factory,
    )

    assert calls == []
    client.create_response(request())
    client.create_response(request())
    assert calls == [{"api_key": "test-key", "timeout": 12.5, "max_retries": 2}]


@pytest.mark.parametrize(
    ("provider_error", "expected_code"),
    [
        (
            openai.AuthenticationError(
                "secret authentication detail",
                response=httpx2.Response(
                    401,
                    request=httpx2.Request("POST", "https://api.openai.test"),
                ),
                body=None,
            ),
            "openai_authentication_failed",
        ),
        (
            openai.BadRequestError(
                "secret rejected-request detail",
                response=httpx2.Response(
                    400,
                    request=httpx2.Request("POST", "https://api.openai.test"),
                ),
                body={"secret": "provider body"},
            ),
            "openai_invalid_request",
        ),
        (
            openai.RateLimitError(
                "secret rate detail",
                response=httpx2.Response(
                    429,
                    request=httpx2.Request("POST", "https://api.openai.test"),
                ),
                body=None,
            ),
            "openai_rate_limited",
        ),
        (
            openai.APITimeoutError(httpx2.Request("POST", "https://api.openai.test")),
            "openai_timeout",
        ),
        (
            openai.APIConnectionError(
                message="secret connection detail",
                request=httpx2.Request("POST", "https://api.openai.test"),
            ),
            "openai_unavailable",
        ),
        (
            openai.InternalServerError(
                "secret server detail",
                response=httpx2.Response(
                    503,
                    request=httpx2.Request("POST", "https://api.openai.test"),
                ),
                body=None,
            ),
            "openai_unavailable",
        ),
        (
            openai.APIResponseValidationError(
                response=httpx2.Response(
                    200,
                    request=httpx2.Request("POST", "https://api.openai.test"),
                ),
                body={"secret": "provider body"},
                message="secret validation detail",
            ),
            "malformed_model_response",
        ),
    ],
)
def test_adapter_translates_documented_provider_errors(
    provider_error: Exception, expected_code: str
) -> None:
    resource = FakeResponsesResource(provider_error)
    client = OpenAIResponsesClient(
        api_key="test-key",
        timeout_seconds=30,
        sdk_client=SimpleNamespace(responses=resource),
    )

    with pytest.raises(ResponsesClientError) as captured:
        client.create_response(request())

    assert captured.value.code == expected_code
    assert "secret" not in str(captured.value)
