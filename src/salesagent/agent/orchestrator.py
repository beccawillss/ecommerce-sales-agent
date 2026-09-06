"""Bounded, application-owned orchestration for one shopper turn."""

import json
from collections import Counter
from dataclasses import dataclass
from typing import Literal, NoReturn, cast

from pydantic import ValidationError

from salesagent.agent.final_output import (
    AgentFinalOutput,
    ConstraintUpdates,
    final_output_text_format,
)
from salesagent.agent.instructions import DEVELOPER_INSTRUCTIONS, PROMPT_VERSION
from salesagent.agent.responses_client import (
    FunctionCallOutput,
    ResponseMessage,
    ResponseRequest,
    ResponsesClient,
    ResponsesClientError,
    ResponseUsage,
)
from salesagent.agent.tools.definitions import ToolName, tool_definitions
from salesagent.agent.tools.dispatcher import ToolDispatcher
from salesagent.agent.tools.models import (
    DiscountData,
    InventoryData,
    ProductData,
    SearchProductsData,
    ToolExecutionError,
    ToolExecutionResult,
)
from salesagent.config import ReasoningEffort
from salesagent.domain.conversation import SessionState
from salesagent.domain.models import DiscountValidationResult

OrchestrationErrorCode = Literal[
    "missing_openai_configuration",
    "openai_authentication_failed",
    "openai_invalid_request",
    "openai_rate_limited",
    "openai_timeout",
    "openai_unavailable",
    "malformed_model_response",
    "invalid_tool_evidence",
    "orchestration_limit_reached",
]

MAX_RESPONSES_PER_TURN = 6
MAX_FUNCTION_CALLS_PER_TURN = 8
MAX_IDENTICAL_CALLS_PER_TURN = 2


@dataclass(frozen=True, slots=True)
class OrchestrationResult:
    """Successful final text and model evidence for one shopper turn."""

    final_text: str
    nominated_product_ids: tuple[str, ...]
    nominated_promotion_code: str | None
    grounded_product_ids: frozenset[str]
    grounded_promotions: tuple[DiscountValidationResult, ...]
    constraint_updates: ConstraintUpdates
    model: str
    prompt_version: str
    usage: ResponseUsage
    tool_calls: tuple["ToolTraceEvidence", ...]
    errors: tuple["TraceErrorEvidence", ...]


@dataclass(frozen=True, slots=True)
class ToolTraceEvidence:
    """One actually dispatched, schema-validated commerce tool result."""

    call_id: str
    tool_name: ToolName
    arguments: dict[str, object]
    result: dict[str, object]
    status: Literal["success", "error"]
    duration_ms: int


@dataclass(frozen=True, slots=True)
class TraceErrorEvidence:
    """Safe evidence for a model call rejected before validated dispatch."""

    code: str
    message: str
    tool_call_id: str | None = None


class AgentOrchestrationError(RuntimeError):
    """Terminal orchestration failure containing only safe internal evidence."""

    def __init__(
        self,
        code: OrchestrationErrorCode,
        *,
        usage: ResponseUsage | None = None,
        tool_calls: tuple[ToolTraceEvidence, ...] = (),
        errors: tuple[TraceErrorEvidence, ...] = (),
        tool_call_id: str | None = None,
    ) -> None:
        super().__init__(code)
        self.code = code
        self.usage = usage or ResponseUsage()
        self.tool_calls = tool_calls
        self.errors = errors
        self.tool_call_id = tool_call_id


class AgentOrchestrator:
    """Run a stateless Responses chain for exactly one shopper turn."""

    def __init__(
        self,
        *,
        responses_client: ResponsesClient,
        dispatcher: ToolDispatcher,
        model: str,
        reasoning_effort: ReasoningEffort,
        max_output_tokens: int,
    ) -> None:
        self._responses_client = responses_client
        self._dispatcher = dispatcher
        self._model = model
        self._reasoning_effort = reasoning_effort
        self._max_output_tokens = max_output_tokens

    @property
    def model(self) -> str:
        """Return the configured model identifier for trace metadata."""
        return self._model

    @property
    def prompt_version(self) -> str:
        """Return the public prompt version without exposing its content."""
        return PROMPT_VERSION

    def run(
        self,
        user_message: str,
        context: SessionState | None = None,
    ) -> OrchestrationResult:
        """Run a bounded direct/tool Responses chain or fail safely."""
        response_input: tuple[ResponseMessage, ...] | tuple[FunctionCallOutput, ...]
        response_input = _initial_messages(context or SessionState(), user_message)
        previous_response_id: str | None = None
        usage = ResponseUsage()
        total_function_calls = 0
        seen_call_ids: set[str] = set()
        signature_counts: Counter[tuple[str, str]] = Counter()
        grounded_product_ids: dict[str, str] = {}
        grounded_promotions: dict[str, DiscountValidationResult] = {}
        tool_calls: list[ToolTraceEvidence] = []
        errors: list[TraceErrorEvidence] = []

        def fail(
            code: OrchestrationErrorCode,
            *,
            tool_call_id: str | None = None,
        ) -> NoReturn:
            raise AgentOrchestrationError(
                code,
                usage=usage,
                tool_calls=tuple(tool_calls),
                errors=tuple(errors),
                tool_call_id=tool_call_id,
            )

        for response_number in range(1, MAX_RESPONSES_PER_TURN + 1):
            request = ResponseRequest(
                input=response_input,
                previous_response_id=previous_response_id,
                model=self._model,
                instructions=DEVELOPER_INSTRUCTIONS,
                tools=tuple(tool_definitions()),
                text_format=final_output_text_format(),
                reasoning_effort=self._reasoning_effort,
                max_output_tokens=self._max_output_tokens,
            )
            try:
                response = self._responses_client.create_response(request)
            except ResponsesClientError as error:
                raise AgentOrchestrationError(
                    error.code,
                    usage=usage,
                    tool_calls=tuple(tool_calls),
                    errors=tuple(errors),
                ) from error

            usage = _add_usage(usage, response.usage)
            if (
                response.status != "completed"
                or response.response_id is None
                or not response.response_id.strip()
            ):
                fail("malformed_model_response")

            calls = response.function_calls
            if not calls:
                try:
                    final_output = AgentFinalOutput.model_validate_json(
                        response.output_text
                    )
                except (ValidationError, ValueError):
                    fail("malformed_model_response")
                return OrchestrationResult(
                    final_text=final_output.message,
                    nominated_product_ids=final_output.nominated_product_ids,
                    nominated_promotion_code=final_output.nominated_promotion_code,
                    grounded_product_ids=frozenset(grounded_product_ids.values()),
                    grounded_promotions=tuple(grounded_promotions.values()),
                    constraint_updates=final_output.constraint_updates,
                    model=self._model,
                    prompt_version=PROMPT_VERSION,
                    usage=usage,
                    tool_calls=tuple(tool_calls),
                    errors=tuple(errors),
                )

            if total_function_calls + len(calls) > MAX_FUNCTION_CALLS_PER_TURN:
                fail("orchestration_limit_reached")
            call_ids = [call.call_id for call in calls]
            if any(call_id is None or not call_id.strip() for call_id in call_ids):
                fail("malformed_model_response")
            valid_call_ids = cast(list[str], call_ids)
            if len(set(valid_call_ids)) != len(valid_call_ids) or any(
                call_id in seen_call_ids for call_id in valid_call_ids
            ):
                fail("malformed_model_response")

            outputs: list[FunctionCallOutput] = []
            seen_call_ids.update(valid_call_ids)
            total_function_calls += len(calls)
            for call, call_id in zip(calls, valid_call_ids, strict=True):
                arguments, invalid_result, signature = _prepare_arguments(
                    call.name, call.arguments_json
                )
                if signature is not None:
                    signature_counts[signature] += 1
                    if signature_counts[signature] > MAX_IDENTICAL_CALLS_PER_TURN:
                        fail(
                            "orchestration_limit_reached",
                            tool_call_id=call_id,
                        )
                result = (
                    invalid_result
                    if invalid_result is not None
                    else self._dispatcher.dispatch(
                        call.name,
                        arguments if arguments is not None else {},
                    )
                )
                serialized_result = cast(
                    dict[str, object], result.model_dump(mode="json")
                )
                if result.arguments is not None:
                    if result.success:
                        try:
                            observed_ids, observed_promotion = _evidence_from_result(
                                call.name, result
                            )
                        except (ValidationError, ValueError):
                            fail("invalid_tool_evidence", tool_call_id=call_id)
                        for product_id in observed_ids:
                            grounded_product_ids.setdefault(
                                product_id.casefold(), product_id
                            )
                        if observed_promotion is not None:
                            promotion_key = observed_promotion.code.casefold()
                            previous = grounded_promotions.get(promotion_key)
                            if previous is not None and previous != observed_promotion:
                                fail("invalid_tool_evidence", tool_call_id=call_id)
                            grounded_promotions.setdefault(
                                promotion_key, observed_promotion
                            )
                    tool_calls.append(
                        ToolTraceEvidence(
                            call_id=call_id,
                            tool_name=cast(ToolName, call.name),
                            arguments=result.arguments,
                            result=serialized_result,
                            status="success" if result.success else "error",
                            duration_ms=result.duration_ms,
                        )
                    )
                else:
                    result_error = result.error
                    if result_error is None:
                        fail("malformed_model_response", tool_call_id=call_id)
                    errors.append(
                        TraceErrorEvidence(
                            code=result_error.code,
                            message=result_error.message,
                            tool_call_id=call_id,
                        )
                    )
                outputs.append(
                    FunctionCallOutput(
                        call_id=call_id,
                        output=json.dumps(
                            serialized_result,
                            sort_keys=True,
                            separators=(",", ":"),
                        ),
                    )
                )

            if response_number == MAX_RESPONSES_PER_TURN:
                break
            response_input = tuple(outputs)
            previous_response_id = response.response_id

        fail("orchestration_limit_reached")


def _prepare_arguments(
    tool_name: str, arguments_json: str
) -> tuple[
    dict[str, object] | None,
    ToolExecutionResult | None,
    tuple[str, str] | None,
]:
    try:
        decoded = json.loads(arguments_json)
    except (json.JSONDecodeError, TypeError):
        return None, _invalid_arguments(tool_name), None
    if not isinstance(decoded, dict):
        return None, _invalid_arguments(tool_name), None
    arguments = cast(dict[str, object], decoded)
    signature = (
        tool_name,
        json.dumps(arguments, sort_keys=True, separators=(",", ":")),
    )
    return arguments, None, signature


def _invalid_arguments(tool_name: str) -> ToolExecutionResult:
    return ToolExecutionResult(
        tool_name=tool_name,
        success=False,
        arguments=None,
        data=None,
        error=ToolExecutionError(
            code="invalid_arguments",
            message="Arguments must be one valid JSON object.",
        ),
        duration_ms=0,
    )


def _evidence_from_result(
    tool_name: str, result: ToolExecutionResult
) -> tuple[tuple[str, ...], DiscountValidationResult | None]:
    """Validate successful tool data and return authoritative turn evidence."""
    if (
        result.tool_name != tool_name
        or result.arguments is None
        or result.data is None
        or result.error is not None
    ):
        raise ValueError("successful tool result envelope is inconsistent")

    if tool_name == "search_products":
        search_data = SearchProductsData.model_validate(result.data)
        if search_data.count != len(search_data.products):
            raise ValueError("search result count is inconsistent")
        return (
            tuple(
                _validated_product_id(product.product_id)
                for product in search_data.products
            ),
            None,
        )
    if tool_name == "get_product":
        product_data = ProductData.model_validate(result.data)
        return ((_validated_product_id(product_data.product_id),), None)
    if tool_name == "check_inventory":
        inventory_data = InventoryData.model_validate(result.data)
        if inventory_data.status == "product_not_found":
            return ((), None)
        return ((_validated_product_id(inventory_data.product_id),), None)
    if tool_name == "validate_discount":
        discount_data = DiscountData.model_validate(result.data)
        promotion = DiscountValidationResult.model_validate(discount_data.model_dump())
        return ((), promotion)
    raise ValueError("successful tool name is not allowlisted")


def _validated_product_id(product_id: str) -> str:
    canonical_id = product_id.strip()
    if not canonical_id:
        raise ValueError("tool result product ID is blank")
    return canonical_id


def _add_usage(left: ResponseUsage, right: ResponseUsage) -> ResponseUsage:
    return ResponseUsage(
        input_tokens=left.input_tokens + right.input_tokens,
        output_tokens=left.output_tokens + right.output_tokens,
        total_tokens=left.total_tokens + right.total_tokens,
    )


def _initial_messages(
    context: SessionState,
    user_message: str,
) -> tuple[ResponseMessage, ...]:
    """Build bounded role-correct history, state data, and current shopper input."""
    messages: list[ResponseMessage] = []
    for turn in context.history:
        messages.append(ResponseMessage(role="user", content=turn.user_message))
        messages.append(
            ResponseMessage(
                role="assistant",
                content=json.dumps(
                    {
                        "message": turn.assistant_message,
                        "recommended_product_ids": list(turn.recommended_product_ids),
                    },
                    sort_keys=True,
                    separators=(",", ":"),
                ),
            )
        )
    constraints = context.resolved_constraints
    state_data: dict[str, object] = {
        "category": constraints.category,
        "activity": constraints.activity,
        "weather": list(constraints.weather),
        "features": list(constraints.features),
        "maximum_price": (
            format(constraints.maximum_price, "f")
            if constraints.maximum_price is not None
            else None
        ),
        "colour": constraints.colour,
        "size": constraints.size,
        "season": constraints.season,
        "priority": constraints.priority,
    }
    messages.append(
        ResponseMessage(
            role="user",
            content=json.dumps(
                {
                    "type": "salesagent_context",
                    "resolved_constraints": state_data,
                },
                sort_keys=True,
                separators=(",", ":"),
            ),
        )
    )
    messages.append(ResponseMessage(role="user", content=user_message))
    return tuple(messages)
