"""Offline checks for the optional live smoke diagnostic."""

import pytest

from salesagent.agent.responses_client import (
    ModelResponse,
    ResponseRequest,
    ResponsesClientError,
    ResponseUsage,
)
from salesagent.config import Settings
from scripts.smoke_openai_agent import run_live_smoke
from tests.fakes import ScriptedResponsesClient


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


def test_success_prints_only_safe_response_and_trace_summary(
    capsys: pytest.CaptureFixture[str],
) -> None:
    client = ScriptedResponsesClient(
        [
            ModelResponse(
                response_id="resp-smoke",
                output_text="I can help you find outdoor gear.",
                function_calls=(),
                usage=ResponseUsage(
                    input_tokens=8,
                    output_tokens=7,
                    total_tokens=15,
                ),
                status="completed",
            )
        ]
    )

    result = run_live_smoke(
        Settings(openai_api_key="sk-test-secret"),
        responses_client=client,
    )

    assert result == 0
    captured = capsys.readouterr()
    assert "message: I can help you find outdoor gear.\n" in captured.out
    assert "model: gpt-5.6-terra\n" in captured.out
    assert "tool_calls: 0\n" in captured.out
    assert "total_tokens: 15\n" in captured.out
    assert "sk-test-secret" not in captured.out
    assert captured.err == ""
