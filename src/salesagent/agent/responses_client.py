"""Narrow, offline-testable boundary around the OpenAI Responses API."""

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Literal, Protocol, cast

import openai
from openai import OpenAI

from salesagent.config import ReasoningEffort

ProviderErrorCode = Literal[
    "missing_openai_configuration",
    "openai_authentication_failed",
    "openai_invalid_request",
    "openai_rate_limited",
    "openai_timeout",
    "openai_unavailable",
    "malformed_model_response",
]


@dataclass(frozen=True, slots=True)
class FunctionCallOutput:
    """Correlated structured output returned for one model function call."""

    call_id: str
    output: str


ResponseInput = str | tuple[FunctionCallOutput, ...]


@dataclass(frozen=True, slots=True)
class ResponseRequest:
    """Application-owned inputs for one Responses API request."""

    input: ResponseInput
    previous_response_id: str | None
    model: str
    instructions: str
    tools: tuple[dict[str, object], ...]
    text_format: dict[str, object]
    reasoning_effort: ReasoningEffort
    max_output_tokens: int


@dataclass(frozen=True, slots=True)
class FunctionCall:
    """One custom function call extracted from provider output."""

    call_id: str | None
    name: str
    arguments_json: str


@dataclass(frozen=True, slots=True)
class ResponseUsage:
    """Token counts reported for one provider response."""

    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0


@dataclass(frozen=True, slots=True)
class ModelResponse:
    """Safe provider response snapshot used by orchestration."""

    response_id: str | None
    output_text: str
    function_calls: tuple[FunctionCall, ...]
    usage: ResponseUsage
    status: str | None
    incomplete_reason: str | None = None


class ResponsesClient(Protocol):
    """Create one model response without exposing SDK types to callers."""

    def create_response(self, request: ResponseRequest) -> ModelResponse:
        """Return an application-owned response snapshot."""
        ...


class ResponsesClientError(RuntimeError):
    """Safe provider/configuration failure with a stable internal category."""

    def __init__(self, code: ProviderErrorCode) -> None:
        super().__init__(code)
        self.code = code


class OpenAIResponsesClient:
    """Map the application request and response shapes to the official SDK."""

    def __init__(
        self,
        *,
        api_key: str | None,
        timeout_seconds: float,
        max_retries: int = 2,
        sdk_client: Any | None = None,
        client_factory: Callable[..., Any] = OpenAI,
    ) -> None:
        self._api_key = api_key
        self._timeout_seconds = timeout_seconds
        self._max_retries = max_retries
        self._client = sdk_client
        self._client_factory = client_factory

    def create_response(self, request: ResponseRequest) -> ModelResponse:
        """Call Responses once and immediately discard raw SDK objects."""
        client = self._get_client()
        response_input: Any
        if isinstance(request.input, str):
            response_input = request.input
        else:
            response_input = [
                {
                    "type": "function_call_output",
                    "call_id": item.call_id,
                    "output": item.output,
                }
                for item in request.input
            ]

        try:
            response = client.responses.create(
                model=request.model,
                input=response_input,
                previous_response_id=request.previous_response_id,
                instructions=request.instructions,
                tools=cast(Any, list(request.tools)),
                text={"format": cast(Any, request.text_format)},
                reasoning={"effort": request.reasoning_effort},
                max_output_tokens=request.max_output_tokens,
                tool_choice="auto",
                parallel_tool_calls=False,
                store=True,
            )
        except openai.AuthenticationError as error:
            raise ResponsesClientError("openai_authentication_failed") from error
        except openai.BadRequestError as error:
            raise ResponsesClientError("openai_invalid_request") from error
        except openai.RateLimitError as error:
            raise ResponsesClientError("openai_rate_limited") from error
        except openai.APITimeoutError as error:
            raise ResponsesClientError("openai_timeout") from error
        except openai.APIResponseValidationError as error:
            raise ResponsesClientError("malformed_model_response") from error
        except (openai.APIConnectionError, openai.APIStatusError) as error:
            raise ResponsesClientError("openai_unavailable") from error

        return self._snapshot(response)

    def _get_client(self) -> Any:
        if self._client is not None:
            return self._client
        if self._api_key is None:
            raise ResponsesClientError("missing_openai_configuration")
        self._client = self._client_factory(
            api_key=self._api_key,
            timeout=self._timeout_seconds,
            max_retries=self._max_retries,
        )
        return self._client

    @staticmethod
    def _snapshot(response: Any) -> ModelResponse:
        raw_output = getattr(response, "output", ())
        output_items = raw_output if isinstance(raw_output, (list, tuple)) else ()
        function_calls = tuple(
            FunctionCall(
                call_id=_optional_string(getattr(item, "call_id", None)),
                name=_string_or_empty(getattr(item, "name", "")),
                arguments_json=_string_or_empty(getattr(item, "arguments", "")),
            )
            for item in output_items
            if getattr(item, "type", None) == "function_call"
        )
        raw_usage = getattr(response, "usage", None)
        usage = ResponseUsage(
            input_tokens=_token_count(getattr(raw_usage, "input_tokens", 0)),
            output_tokens=_token_count(getattr(raw_usage, "output_tokens", 0)),
            total_tokens=_token_count(getattr(raw_usage, "total_tokens", 0)),
        )
        incomplete_details = getattr(response, "incomplete_details", None)
        return ModelResponse(
            response_id=_optional_string(getattr(response, "id", None)),
            output_text=_string_or_empty(getattr(response, "output_text", "")),
            function_calls=function_calls,
            usage=usage,
            status=_optional_string(getattr(response, "status", None)),
            incomplete_reason=_optional_string(
                getattr(incomplete_details, "reason", None)
            ),
        )


def _optional_string(value: object) -> str | None:
    return value if isinstance(value, str) else None


def _string_or_empty(value: object) -> str:
    return value if isinstance(value, str) else ""


def _token_count(value: object) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise ResponsesClientError("malformed_model_response")
    return value
