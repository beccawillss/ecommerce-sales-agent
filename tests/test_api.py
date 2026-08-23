"""Contract-oriented tests for the deterministic V1 HTTP API shell."""

from collections.abc import Iterator
from datetime import datetime
from typing import Any
from uuid import UUID

import pytest
from fastapi.testclient import TestClient

from salesagent.config import Settings
from salesagent.main import create_app


@pytest.fixture
def client() -> Iterator[TestClient]:
    with TestClient(create_app(Settings(enable_eval_traces=True))) as test_client:
        yield test_client


def test_new_session_returns_contract_shaped_stub_response(
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
        "message": "Sales Agent is not configured yet.",
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
    assert trace["model"] == "stub"
    assert trace["prompt_version"] == "none"
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
        "input_tokens": 0,
        "output_tokens": 0,
        "total_tokens": 0,
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

    with TestClient(create_app()) as disabled_client:
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
