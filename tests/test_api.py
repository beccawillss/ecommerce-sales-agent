"""Contract-oriented tests for the deterministic V1 HTTP API shell."""

import json
from collections.abc import Iterator
from datetime import datetime
from typing import Any
from uuid import UUID

import pytest
from fastapi.testclient import TestClient

from salesagent.agent.final_output import (
    ConstraintUpdates,
    MoneyTextUpdate,
    TextListUpdate,
    TextUpdate,
)
from salesagent.agent.responses_client import (
    FunctionCall,
    ModelResponse,
    ResponsesClientError,
    ResponseUsage,
)
from salesagent.config import Settings
from salesagent.main import create_app
from tests.fakes import ScriptedResponsesClient, final_output_json


def constraint_updates(**values: object) -> ConstraintUpdates:
    payload = ConstraintUpdates.retain_all().model_dump()
    payload.update(values)
    return ConstraintUpdates.model_validate(payload)


def direct_response(
    index: int = 1, message: str = "How can I help with your kit?"
) -> ModelResponse:
    return ModelResponse(
        response_id=f"resp-direct-{index}",
        output_text=final_output_json(message),
        function_calls=(),
        usage=ResponseUsage(input_tokens=4, output_tokens=6, total_tokens=10),
        status="completed",
    )


@pytest.fixture
def client() -> Iterator[TestClient]:
    model_client = ScriptedResponsesClient(
        [direct_response(index) for index in range(1, 20)]
    )
    application = create_app(
        Settings(enable_eval_traces=True),
        responses_client=model_client,
    )
    with TestClient(application) as test_client:
        yield test_client


def test_new_session_returns_contract_shaped_model_response(
    client: TestClient,
) -> None:
    response = client.post(
        "/api/v1/chat",
        json={"message": "I need a waterproof jacket"},
    )

    assert response.status_code == 200
    body = response.json()
    UUID(body["session_id"])
    UUID(body["trace_id"])
    assert body == {
        "session_id": body["session_id"],
        "trace_id": body["trace_id"],
        "message": "How can I help with your kit?",
        "recommendations": [],
        "promotion": None,
        "pricing": None,
    }


def test_supplied_session_id_is_preserved(client: TestClient) -> None:
    response = client.post(
        "/api/v1/chat",
        json={
            "session_id": "existing-session-id",
            "message": "I'd prefer Ocean Blue",
        },
    )

    assert response.status_code == 200
    assert response.json()["session_id"] == "existing-session-id"


def test_empty_session_id_is_rejected(client: TestClient) -> None:
    response = client.post(
        "/api/v1/chat",
        json={"session_id": "", "message": "Hello"},
    )

    assert response.status_code == 422


def test_null_session_id_generates_a_new_session(client: TestClient) -> None:
    response = client.post(
        "/api/v1/chat",
        json={"session_id": None, "message": "Hello"},
    )

    assert response.status_code == 200
    UUID(response.json()["session_id"])


def test_each_successful_chat_receives_a_unique_trace_id(
    client: TestClient,
) -> None:
    first = client.post("/api/v1/chat", json={"message": "First"}).json()
    second = client.post("/api/v1/chat", json={"message": "Second"}).json()

    assert first["trace_id"] != second["trace_id"]


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"message": ""},
        {"message": "   "},
        {"message": "x" * 4001},
        {"message": "Hello", "unexpected": True},
    ],
)
def test_malformed_chat_requests_are_rejected(
    client: TestClient, payload: dict[str, Any]
) -> None:
    response = client.post("/api/v1/chat", json=payload)

    assert response.status_code == 422


def test_chat_trace_can_be_retrieved_by_returned_id(client: TestClient) -> None:
    chat_response = client.post(
        "/api/v1/chat",
        json={"session_id": "trace-session", "message": "Keep this safe"},
        headers={"Authorization": "Bearer must-not-be-traced"},
    ).json()

    response = client.get(f"/api/v1/traces/{chat_response['trace_id']}")

    assert response.status_code == 200
    trace = response.json()
    assert trace["trace_id"] == chat_response["trace_id"]
    assert trace["session_id"] == "trace-session"
    assert trace["turn_index"] == 1
    assert trace["user_message"] == "Keep this safe"
    assert trace["model"] == "gpt-5.6-terra"
    assert trace["prompt_version"] == "phase6-v2"
    assert trace["resolved_constraints"] == {
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
    assert trace["constraint_changes"] == []
    assert trace["tool_calls"] == []
    assert trace["recommended_product_ids"] == []
    assert trace["promotion"] is None
    assert trace["pricing"] is None
    assert trace["token_usage"] == {
        "input_tokens": 4,
        "output_tokens": 6,
        "total_tokens": 10,
    }
    assert trace["errors"] == []
    assert trace["latency_ms"] >= 0
    assert datetime.fromisoformat(trace["timestamp"]).tzinfo is not None
    assert trace["recommendation_validation"] == {
        "all_products_exist": True,
        "prices_match_catalogue": True,
        "urls_match_catalogue": True,
        "stock_claims_validated": True,
        "validation_errors": [],
    }
    assert "authorization" not in response.text.casefold()
    assert "must-not-be-traced" not in response.text


def test_turn_indices_increment_independently_per_session(
    client: TestClient,
) -> None:
    first_a = client.post(
        "/api/v1/chat", json={"session_id": "session-a", "message": "A1"}
    ).json()
    first_b = client.post(
        "/api/v1/chat", json={"session_id": "session-b", "message": "B1"}
    ).json()
    second_a = client.post(
        "/api/v1/chat", json={"session_id": "session-a", "message": "A2"}
    ).json()

    trace_a1 = client.get(f"/api/v1/traces/{first_a['trace_id']}").json()
    trace_b1 = client.get(f"/api/v1/traces/{first_b['trace_id']}").json()
    trace_a2 = client.get(f"/api/v1/traces/{second_a['trace_id']}").json()

    assert trace_a1["turn_index"] == 1
    assert trace_b1["turn_index"] == 1
    assert trace_a2["turn_index"] == 2


def test_unknown_trace_returns_not_found(client: TestClient) -> None:
    response = client.get("/api/v1/traces/nonexistent-id")

    assert response.status_code == 404
    assert response.json() == {"detail": "Trace not found"}


def test_disabled_trace_route_does_not_expose_trace_contents(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SALESAGENT_ENABLE_EVAL_TRACES", "false")

    model_client = ScriptedResponsesClient([direct_response()])
    with TestClient(create_app(responses_client=model_client)) as disabled_client:
        chat_response = disabled_client.post(
            "/api/v1/chat", json={"message": "Private turn"}
        ).json()

        response = disabled_client.get(f"/api/v1/traces/{chat_response['trace_id']}")
        openapi = disabled_client.get("/openapi.json").json()

    assert response.status_code == 404
    assert "/api/v1/traces/{trace_id}" not in openapi["paths"]


def test_openapi_exposes_contract_paths_and_chat_limits(client: TestClient) -> None:
    openapi = client.get("/openapi.json").json()
    chat_request = openapi["components"]["schemas"]["ChatRequest"]
    chat_response = openapi["components"]["schemas"]["ChatResponse"]
    trace_response = openapi["components"]["schemas"]["TraceResponse"]
    product_recommendation = openapi["components"]["schemas"]["ProductRecommendation"]
    recommendation_validation = openapi["components"]["schemas"][
        "RecommendationValidation"
    ]
    message_schema = chat_request["properties"]["message"]

    assert "/api/v1/chat" in openapi["paths"]
    assert "/api/v1/traces/{trace_id}" in openapi["paths"]
    assert message_schema["minLength"] == 1
    assert message_schema["maxLength"] == 4000
    assert set(chat_response["required"]) == {
        "session_id",
        "trace_id",
        "message",
        "recommendations",
    }
    assert chat_response["properties"]["recommendations"]["maxItems"] == 3
    assert set(product_recommendation["required"]) == {
        "product_id",
        "name",
        "price",
        "currency",
        "product_url",
        "availability",
    }
    assert product_recommendation["properties"]["availability"]["enum"] == [
        "in_stock",
        "out_of_stock",
        "partial",
        "unknown",
    ]
    assert set(recommendation_validation["required"]) == {
        "all_products_exist",
        "prices_match_catalogue",
        "urls_match_catalogue",
        "stock_claims_validated",
    }
    assert {
        "trace_id",
        "session_id",
        "timestamp",
        "turn_index",
        "user_message",
        "model",
        "prompt_version",
        "resolved_constraints",
        "constraint_changes",
        "tool_calls",
        "recommendation_validation",
        "recommended_product_ids",
        "latency_ms",
        "token_usage",
        "errors",
    } == set(trace_response["required"])
    assert (
        openapi["components"]["schemas"]["ProductRecommendation"]["properties"][
            "price"
        ]["type"]
        == "number"
    )


def test_chat_endpoint_runs_real_dispatcher_tool_loop_offline() -> None:
    model_client = ScriptedResponsesClient(
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
                usage=ResponseUsage(input_tokens=5, output_tokens=3, total_tokens=8),
                status="completed",
            ),
            ModelResponse(
                response_id="resp-final",
                output_text=final_output_json(
                    "I found verified cycling options.", ["JKT-005", "jkt-002"]
                ),
                function_calls=(),
                usage=ResponseUsage(input_tokens=7, output_tokens=4, total_tokens=11),
                status="completed",
            ),
        ]
    )
    application = create_app(
        Settings(enable_eval_traces=True), responses_client=model_client
    )

    with TestClient(application) as test_client:
        response = test_client.post(
            "/api/v1/chat", json={"message": "Find a cycling jacket"}
        )
        body = response.json()
        trace = test_client.get(f"/api/v1/traces/{body['trace_id']}").json()

    assert response.status_code == 200
    assert body["message"] == "I found verified cycling options."
    assert body["recommendations"] == [
        {
            "product_id": "JKT-005",
            "name": "Trail Breeze Wind Shell",
            "price": 85.0,
            "currency": "GBP",
            "product_url": "/products/trail-breeze",
            "availability": "in_stock",
            "matched_variant": None,
        },
        {
            "product_id": "JKT-002",
            "name": "Velo Lite Windbreaker",
            "price": 75.0,
            "currency": "GBP",
            "product_url": "/products/velo-lite",
            "availability": "out_of_stock",
            "matched_variant": None,
        },
    ]
    assert body["promotion"] is None
    assert body["pricing"] is None
    assert trace["token_usage"] == {
        "input_tokens": 12,
        "output_tokens": 7,
        "total_tokens": 19,
    }
    assert trace["tool_calls"][0]["sequence"] == 1
    assert trace["tool_calls"][0]["tool_call_id"] == "call-search"
    assert trace["tool_calls"][0]["tool_name"] == "search_products"
    assert trace["tool_calls"][0]["arguments"] == {
        "category": None,
        "activity": "cycling",
        "weather": [],
        "features": [],
        "maximum_price": None,
        "colour": None,
        "size": None,
        "in_stock_only": False,
    }
    assert trace["tool_calls"][0]["result"]["success"] is True
    assert trace["recommended_product_ids"] == ["JKT-005", "JKT-002"]
    assert trace["recommendation_validation"] == {
        "all_products_exist": True,
        "prices_match_catalogue": True,
        "urls_match_catalogue": True,
        "stock_claims_validated": True,
        "validation_errors": [],
    }


def test_each_chat_turn_starts_a_new_responses_chain() -> None:
    model_client = ScriptedResponsesClient([direct_response(1), direct_response(2)])
    application = create_app(
        Settings(enable_eval_traces=True), responses_client=model_client
    )

    with TestClient(application) as test_client:
        first = test_client.post(
            "/api/v1/chat",
            json={"session_id": "same-session", "message": "First"},
        )
        second = test_client.post(
            "/api/v1/chat",
            json={"session_id": "same-session", "message": "Second"},
        )

    assert first.status_code == 200
    assert second.status_code == 200
    assert [request.previous_response_id for request in model_client.requests] == [
        None,
        None,
    ]
    first_input, second_input = [request.input for request in model_client.requests]
    assert [item.role for item in first_input] == ["user", "user"]
    assert first_input[-1].content == "First"
    assert [item.role for item in second_input] == [
        "user",
        "assistant",
        "user",
        "user",
    ]
    assert second_input[0].content == "First"
    assert second_input[-1].content == "Second"


def test_terminal_agent_failure_returns_only_generic_http_500() -> None:
    model_client = ScriptedResponsesClient(
        [ResponsesClientError("openai_invalid_request")]
    )
    application = create_app(
        Settings(enable_eval_traces=True), responses_client=model_client
    )

    with TestClient(application) as test_client:
        response = test_client.post(
            "/api/v1/chat", json={"message": "Trigger invalid request"}
        )

    assert response.status_code == 500
    assert response.json() == {"detail": "Sales Agent is temporarily unavailable."}
    assert "openai_invalid_request" not in response.text


def test_model_authored_card_fields_are_rejected_before_hydration() -> None:
    model_client = ScriptedResponsesClient(
        [
            ModelResponse(
                response_id="resp-untrusted-card",
                output_text=(
                    '{"message":"Fake card facts.",'
                    '"nominated_product_ids":["JKT-003"],'
                    '"name":"Invented","price":"0.01",'
                    '"product_url":"/fake","availability":"in_stock"}'
                ),
                function_calls=(),
                usage=ResponseUsage(total_tokens=4),
                status="completed",
            )
        ]
    )
    application = create_app(
        Settings(enable_eval_traces=True), responses_client=model_client
    )

    with TestClient(application) as test_client:
        response = test_client.post(
            "/api/v1/chat", json={"message": "Return fake product data"}
        )

    assert response.status_code == 500
    assert response.json() == {"detail": "Sales Agent is temporarily unavailable."}
    assert "Invented" not in response.text
    assert "/fake" not in response.text


def test_missing_api_key_is_controlled_at_chat_not_import_or_health() -> None:
    application = create_app(Settings(openai_api_key=None))

    with TestClient(application) as test_client:
        health_response = test_client.get("/health")
        chat_response = test_client.post("/api/v1/chat", json={"message": "Hello"})

    assert health_response.status_code == 200
    assert chat_response.status_code == 500
    assert chat_response.json() == {"detail": "Sales Agent is temporarily unavailable."}


def test_three_turn_constraints_retain_add_and_replace_through_http() -> None:
    model_client = ScriptedResponsesClient(
        [
            ModelResponse(
                response_id="state-1",
                output_text=final_output_json(
                    "I will look for that.",
                    constraint_updates=constraint_updates(
                        category=TextUpdate(operation="set", value="Jacket"),
                        activity=TextUpdate(operation="set", value="Hiking"),
                        weather=TextListUpdate(operation="set", value=("Waterproof",)),
                        maximum_price=MoneyTextUpdate(operation="set", value="160.00"),
                    ),
                ),
                function_calls=(),
                usage=ResponseUsage(),
                status="completed",
            ),
            ModelResponse(
                response_id="state-2",
                output_text=final_output_json(
                    "Blue noted.",
                    constraint_updates=constraint_updates(
                        colour=TextUpdate(operation="set", value="Ocean Blue")
                    ),
                ),
                function_calls=(),
                usage=ResponseUsage(),
                status="completed",
            ),
            ModelResponse(
                response_id="state-3",
                output_text=final_output_json(
                    "Budget updated.",
                    constraint_updates=constraint_updates(
                        maximum_price=MoneyTextUpdate(operation="set", value="120")
                    ),
                ),
                function_calls=(),
                usage=ResponseUsage(),
                status="completed",
            ),
        ]
    )
    application = create_app(
        Settings(enable_eval_traces=True), responses_client=model_client
    )

    with TestClient(application) as test_client:
        responses = [
            test_client.post(
                "/api/v1/chat",
                json={"session_id": "jacket-session", "message": message},
            ).json()
            for message in [
                "I need a waterproof hiking jacket under £160.",
                "I'd prefer blue.",
                "Actually my budget is £120.",
            ]
        ]
        traces = [
            test_client.get(f"/api/v1/traces/{response['trace_id']}").json()
            for response in responses
        ]

    assert traces[0]["resolved_constraints"] == {
        "category": "Jacket",
        "activity": "Hiking",
        "weather": ["Waterproof"],
        "features": [],
        "maximum_price": 160.0,
        "colour": None,
        "size": None,
        "season": None,
        "priority": None,
    }
    assert [change["field"] for change in traces[0]["constraint_changes"]] == [
        "category",
        "activity",
        "weather",
        "maximum_price",
    ]
    assert [change["field"] for change in traces[1]["constraint_changes"]] == ["colour"]
    assert traces[2]["resolved_constraints"] == {
        **traces[1]["resolved_constraints"],
        "maximum_price": 120.0,
    }
    assert traces[2]["constraint_changes"] == [
        {"field": "maximum_price", "previous": 160.0, "current": 120.0}
    ]


def test_clear_and_independent_session_state_do_not_leak() -> None:
    model_client = ScriptedResponsesClient(
        [
            ModelResponse(
                response_id="a-set",
                output_text=final_output_json(
                    "Set.",
                    constraint_updates=constraint_updates(
                        colour=TextUpdate(operation="set", value="Blue")
                    ),
                ),
                function_calls=(),
                usage=ResponseUsage(),
                status="completed",
            ),
            direct_response(2),
            ModelResponse(
                response_id="a-clear",
                output_text=final_output_json(
                    "Cleared.",
                    constraint_updates=constraint_updates(
                        colour=TextUpdate(operation="clear", value=None)
                    ),
                ),
                function_calls=(),
                usage=ResponseUsage(),
                status="completed",
            ),
        ]
    )
    application = create_app(
        Settings(enable_eval_traces=True), responses_client=model_client
    )

    with TestClient(application) as test_client:
        a1 = test_client.post(
            "/api/v1/chat", json={"session_id": "a", "message": "Blue"}
        ).json()
        b1 = test_client.post(
            "/api/v1/chat", json={"session_id": "b", "message": "Hello"}
        ).json()
        a2 = test_client.post(
            "/api/v1/chat", json={"session_id": "a", "message": "Any colour"}
        ).json()
        traces = [
            test_client.get(f"/api/v1/traces/{item['trace_id']}").json()
            for item in (a1, b1, a2)
        ]

    assert traces[0]["resolved_constraints"]["colour"] == "Blue"
    assert traces[1]["resolved_constraints"]["colour"] is None
    assert traces[1]["turn_index"] == 1
    assert traces[2]["resolved_constraints"]["colour"] is None
    assert traces[2]["constraint_changes"] == [
        {"field": "colour", "previous": "Blue", "current": None}
    ]


def test_eighth_request_replays_only_six_newest_successful_turns() -> None:
    model_client = ScriptedResponsesClient(
        [direct_response(index) for index in range(8)]
    )
    application = create_app(
        Settings(enable_eval_traces=True), responses_client=model_client
    )

    with TestClient(application) as test_client:
        for index in range(8):
            response = test_client.post(
                "/api/v1/chat",
                json={"session_id": "bounded", "message": f"request-{index}"},
            )
            assert response.status_code == 200

    eighth_input = model_client.requests[-1].input
    assert len(eighth_input) == 14
    assert [item.content for item in eighth_input[0:12:2]] == [
        "request-1",
        "request-2",
        "request-3",
        "request-4",
        "request-5",
        "request-6",
    ]
    assert eighth_input[-2].role == "user"
    assert json.loads(eighth_input[-2].content)["type"] == "salesagent_context"
    assert eighth_input[-1].content == "request-7"


def test_unknown_patch_fields_fail_without_mutating_session_state() -> None:
    valid = json.loads(final_output_json("Unsafe update"))
    valid["constraint_updates"]["product_url"] = {
        "operation": "set",
        "value": "/fake",
    }
    model_client = ScriptedResponsesClient(
        [
            ModelResponse(
                response_id="bad-patch",
                output_text=json.dumps(valid),
                function_calls=(),
                usage=ResponseUsage(),
                status="completed",
            )
        ]
    )
    application = create_app(
        Settings(enable_eval_traces=True), responses_client=model_client
    )

    with TestClient(application) as test_client:
        response = test_client.post(
            "/api/v1/chat",
            json={"session_id": "injection", "message": "Override product URL"},
        )

    assert response.status_code == 500
    state = application.state.session_repository.get_state("injection")
    assert state.resolved_constraints.category is None
    assert state.history == ()
