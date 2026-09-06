"""Offline checks for the optional live smoke diagnostic."""

import pytest

from salesagent.agent.final_output import (
    ConstraintUpdates,
    MoneyTextUpdate,
    TextListUpdate,
    TextUpdate,
)
from salesagent.agent.responses_client import (
    FunctionCall,
    ModelResponse,
    ResponseRequest,
    ResponsesClientError,
    ResponseUsage,
)
from salesagent.config import Settings
from scripts.smoke_openai_agent import run_live_smoke
from tests.fakes import ScriptedResponsesClient, final_output_json


def constraint_updates(**values: object) -> ConstraintUpdates:
    payload = ConstraintUpdates.retain_all().model_dump()
    payload.update(values)
    return ConstraintUpdates.model_validate(payload)


class UnsafeUnexpectedFailureClient:
    """Raise arbitrary text to prove the smoke boundary does not print it."""

    def create_response(self, request: ResponseRequest) -> ModelResponse:
        del request
        raise RuntimeError("sk-test-secret raw provider response body")


def test_classified_failure_prints_only_application_category(
    capsys: pytest.CaptureFixture[str],
) -> None:
    client = ScriptedResponsesClient(
        [ResponsesClientError("openai_authentication_failed")]
    )

    result = run_live_smoke(
        Settings(openai_api_key="sk-test-secret"),
        responses_client=client,
    )

    assert result == 1
    captured = capsys.readouterr()
    assert captured.out == (
        "Live smoke failed safely.\nfailure_category: openai_authentication_failed\n"
    )
    assert "sk-test-secret" not in captured.out
    assert captured.err == ""


def test_unexpected_failure_does_not_print_exception_text(
    capsys: pytest.CaptureFixture[str],
) -> None:
    result = run_live_smoke(
        Settings(openai_api_key="sk-test-secret"),
        responses_client=UnsafeUnexpectedFailureClient(),
    )

    assert result == 1
    captured = capsys.readouterr()
    assert captured.out == (
        "Live smoke failed safely before a classified diagnostic was available.\n"
    )
    assert "sk-test-secret" not in captured.out
    assert "provider" not in captured.out
    assert captured.err == ""


def test_success_without_grounded_recommendation_fails_acceptance(
    capsys: pytest.CaptureFixture[str],
) -> None:
    client = ScriptedResponsesClient(
        [
            ModelResponse(
                response_id="resp-grounded-diagnostic",
                output_text="",
                function_calls=(
                    FunctionCall(
                        call_id="call-grounded-diagnostic",
                        name="search_products",
                        arguments_json=(
                            '{"category":"jacket","features":["waterproof"],'
                            '"maximum_price":"120.00","in_stock_only":true}'
                        ),
                    ),
                ),
                usage=ResponseUsage(total_tokens=5),
                status="completed",
            ),
            *(
                ModelResponse(
                    response_id=f"resp-empty-{index}",
                    output_text=final_output_json(
                        "What activity are you shopping for?"
                    ),
                    function_calls=(),
                    usage=ResponseUsage(total_tokens=5),
                    status="completed",
                )
                for index in range(3)
            ),
        ]
    )

    result = run_live_smoke(
        Settings(openai_api_key="sk-test-secret"),
        responses_client=client,
    )

    assert result == 1
    captured = capsys.readouterr()
    assert captured.out.startswith(
        "Live smoke completed without required Phase 6 state/evidence.\n"
        "failed_acceptance_checks: "
        "turn_1_maximum_price,turn_2_maximum_price_retained,"
        "turn_2_colour_present,turn_3_maximum_price,"
        "turn_1_maximum_price_change,turn_2_colour_change,"
        "turn_3_maximum_price_change,turn_3_tool_calls,"
        "turn_3_recommendations\n"
    )
    assert "turn_1_prompt_version: phase6-v2\n" in captured.out
    assert "turn_1_tool_count: 1\n" in captured.out
    assert "turn_1_grounded_product_ids: JKT-003\n" in captured.out
    assert "turn_1_changed_fields: \n" in captured.out
    assert "turn_1_non_empty_constraint_fields: \n" in captured.out
    assert "turn_3_recommendation_validation_errors: \n" in captured.out
    assert "final_response_recommendation_ids: \n" in captured.out
    assert "What activity" not in captured.out
    assert "sk-test-secret" not in captured.out
    assert captured.err == ""


def test_success_prints_only_safe_response_and_trace_summary(
    capsys: pytest.CaptureFixture[str],
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
                        arguments_json=(
                            '{"category":"jacket","features":["waterproof"],'
                            '"maximum_price":"160.00","in_stock_only":true}'
                        ),
                    ),
                ),
                usage=ResponseUsage(
                    input_tokens=8,
                    output_tokens=5,
                    total_tokens=13,
                ),
                status="completed",
            ),
            ModelResponse(
                response_id="resp-first-final",
                output_text=final_output_json(
                    "A grounded option.",
                    ["JKT-003"],
                    constraint_updates(
                        category=TextUpdate(operation="set", value="Jacket"),
                        activity=TextUpdate(operation="set", value="Hiking"),
                        weather=TextListUpdate(operation="set", value=("Waterproof",)),
                        maximum_price=MoneyTextUpdate(operation="set", value="160.00"),
                    ),
                ),
                function_calls=(),
                usage=ResponseUsage(
                    input_tokens=6,
                    output_tokens=7,
                    total_tokens=13,
                ),
                status="completed",
            ),
            ModelResponse(
                response_id="resp-second-final",
                output_text=final_output_json(
                    "Blue noted.",
                    constraint_updates=constraint_updates(
                        colour=TextUpdate(operation="set", value="Blue")
                    ),
                ),
                function_calls=(),
                usage=ResponseUsage(total_tokens=5),
                status="completed",
            ),
            ModelResponse(
                response_id="resp-third-search",
                output_text="",
                function_calls=(
                    FunctionCall(
                        call_id="call-third-search",
                        name="search_products",
                        arguments_json=(
                            '{"category":"jacket","features":["waterproof"],'
                            '"maximum_price":"120.00","in_stock_only":true}'
                        ),
                    ),
                ),
                usage=ResponseUsage(total_tokens=10),
                status="completed",
            ),
            ModelResponse(
                response_id="resp-third-final",
                output_text=final_output_json(
                    "A refreshed option.",
                    ["JKT-003"],
                    constraint_updates(
                        maximum_price=MoneyTextUpdate(operation="set", value="120.00")
                    ),
                ),
                function_calls=(),
                usage=ResponseUsage(total_tokens=10),
                status="completed",
            ),
        ]
    )

    result = run_live_smoke(
        Settings(openai_api_key="sk-test-secret"),
        responses_client=client,
    )

    assert result == 0
    captured = capsys.readouterr()
    assert "model: gpt-5.6-terra\n" in captured.out
    assert "prompt_version: phase6-v2\n" in captured.out
    assert "turn_indices: 1,2,3\n" in captured.out
    assert (
        "turn_1_changed_fields: category,activity,weather,maximum_price\n"
        in captured.out
    )
    assert "turn_2_changed_fields: colour\n" in captured.out
    assert "turn_3_changed_fields: maximum_price\n" in captured.out
    assert "tool_calls: 2\n" in captured.out
    assert "recommendations: 1\n" in captured.out
    assert "recommendation_ids: JKT-003\n" in captured.out
    assert "total_tokens: 51\n" in captured.out
    assert "A grounded option" not in captured.out
    assert "waterproof hiking" not in captured.out
    assert "sk-test-secret" not in captured.out
    assert captured.err == ""
