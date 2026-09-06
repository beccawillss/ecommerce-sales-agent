"""Explicit, optional live smoke check for Phase 7 promotion pricing."""

from decimal import ROUND_HALF_UP, Decimal
from typing import cast

from salesagent.agent.responses_client import ResponsesClient
from salesagent.agent.tools.models import (
    InventoryData,
    ProductData,
    SearchProductsData,
)
from salesagent.api.models import ChatRequest, ChatResponse, TraceResponse
from salesagent.config import Settings
from salesagent.main import create_app
from salesagent.repositories.traces import InMemoryTraceRepository
from salesagent.services.chat import ChatService, ChatServiceError

SMOKE_MESSAGES = (
    "I need a waterproof hiking jacket under £160.",
    "I'd prefer blue. Keep my other requirements.",
    "Actually make the budget £120, recommend the best match, and apply WELCOME10.",
)

GBP_QUANTUM = Decimal("0.01")


def _non_empty_constraint_fields(trace: TraceResponse) -> list[str]:
    constraints = trace.resolved_constraints
    values = constraints.model_dump()
    return [
        field for field, value in values.items() if value is not None and value != []
    ]


def _grounded_product_ids(trace: TraceResponse) -> list[str]:
    """Recover the compact current-turn grounding set from validated traces."""
    grounded_ids: dict[str, str] = {}
    for tool_call in trace.tool_calls:
        if tool_call.status != "success":
            continue
        result_data = tool_call.result.get("data")
        if not isinstance(result_data, dict):
            continue
        if tool_call.tool_name == "search_products":
            result = SearchProductsData.model_validate(result_data)
            product_ids = [product.product_id for product in result.products]
        elif tool_call.tool_name == "get_product":
            product_ids = [ProductData.model_validate(result_data).product_id]
        elif tool_call.tool_name == "check_inventory":
            inventory = InventoryData.model_validate(result_data)
            product_ids = (
                []
                if inventory.status == "product_not_found"
                else [inventory.product_id]
            )
        else:
            product_ids = []
        for product_id in product_ids:
            grounded_ids.setdefault(product_id.casefold(), product_id)
    return list(grounded_ids.values())


def _pricing_is_consistent(
    response: ChatResponse,
    trace: TraceResponse,
) -> bool:
    """Check Phase 7 relationships without printing authoritative amounts."""
    promotion = response.promotion
    pricing = response.pricing
    if (
        promotion is None
        or pricing is None
        or trace.promotion != promotion
        or trace.pricing != pricing
        or not response.recommendations
        or not trace.recommended_product_ids
        or pricing.product_id != response.recommendations[0].product_id
        or pricing.product_id != trace.recommended_product_ids[0]
        or pricing.base_price != response.recommendations[0].price
        or pricing.discount_code != promotion.code
        or pricing.discount_percent != promotion.discount_percent
        or pricing.discount_percent is None
    ):
        return False
    discount = (
        pricing.base_price * pricing.discount_percent / Decimal("100")
    ).quantize(
        GBP_QUANTUM,
        rounding=ROUND_HALF_UP,
    )
    expected_final = (pricing.base_price - discount).quantize(
        GBP_QUANTUM,
        rounding=ROUND_HALF_UP,
    )
    return pricing.final_price == expected_final


def _print_safe_failure_diagnostics(
    traces: list[TraceResponse],
    final_recommendation_ids: list[str],
    failed_checks: list[str],
) -> None:
    """Print bounded trace summaries without shopper/model prose or raw payloads."""
    print(f"failed_acceptance_checks: {','.join(failed_checks)}")
    for trace in traces:
        turn_index = trace.turn_index
        tool_names = [item.tool_name for item in trace.tool_calls]
        changed_fields = [item.field for item in trace.constraint_changes]
        recommendation_ids = trace.recommended_product_ids
        grounded_product_ids = _grounded_product_ids(trace)
        validation_errors = trace.recommendation_validation.validation_errors
        promotion = trace.promotion
        pricing = trace.pricing
        print(f"turn_{turn_index}_prompt_version: {trace.prompt_version}")
        print(f"turn_{turn_index}_tool_count: {len(tool_names)}")
        print(f"turn_{turn_index}_tool_names: {','.join(tool_names)}")
        print(
            f"turn_{turn_index}_grounded_product_ids: {','.join(grounded_product_ids)}"
        )
        print(f"turn_{turn_index}_changed_fields: {','.join(changed_fields)}")
        print(
            f"turn_{turn_index}_non_empty_constraint_fields: "
            f"{','.join(_non_empty_constraint_fields(trace))}"
        )
        print(f"turn_{turn_index}_recommendation_ids: {','.join(recommendation_ids)}")
        print(
            f"turn_{turn_index}_recommendation_validation_errors: "
            f"{','.join(validation_errors)}"
        )
        print(
            f"turn_{turn_index}_promotion_code: "
            f"{promotion.code if promotion is not None else ''}"
        )
        print(
            f"turn_{turn_index}_promotion_reason: "
            f"{promotion.reason if promotion is not None else ''}"
        )
        print(
            f"turn_{turn_index}_pricing_product_id: "
            f"{pricing.product_id if pricing is not None else ''}"
        )
    print(f"final_response_recommendation_ids: {','.join(final_recommendation_ids)}")


def run_live_smoke(
    settings: Settings,
    *,
    responses_client: ResponsesClient | None = None,
) -> int:
    """Run the assembled chat service and print only safe diagnostic fields."""
    try:
        application = create_app(
            settings,
            responses_client=responses_client,
        )
        chat_service = cast(ChatService, application.state.chat_service)
        trace_repository = cast(
            InMemoryTraceRepository,
            application.state.trace_repository,
        )
        responses = []
        traces = []
        session_id: str | None = None
        for message in SMOKE_MESSAGES:
            response = chat_service.chat(
                ChatRequest(session_id=session_id, message=message)
            )
            session_id = response.session_id
            trace = trace_repository.get(response.trace_id)
            if trace is None:
                print("Live chat succeeded, but its safe trace could not be retrieved.")
                return 1
            responses.append(response)
            traces.append(trace)
    except ChatServiceError as error:
        print("Live smoke failed safely.")
        print(f"failure_category: {error.code}")
        return 1
    except Exception:
        # Never let an unexpected provider or SDK error become terminal output.
        print("Live smoke failed safely before a classified diagnostic was available.")
        return 1

    first_trace, second_trace, final_trace = traces
    final_response = responses[-1]
    recommendation_ids = [item.product_id for item in final_response.recommendations]
    failed_checks = [
        name
        for name, passed in (
            ("turn_indices", [trace.turn_index for trace in traces] == [1, 2, 3]),
            (
                "turn_1_maximum_price",
                first_trace.resolved_constraints.maximum_price == 160,
            ),
            (
                "turn_2_maximum_price_retained",
                second_trace.resolved_constraints.maximum_price == 160,
            ),
            (
                "turn_2_colour_present",
                second_trace.resolved_constraints.colour is not None,
            ),
            (
                "turn_3_maximum_price",
                final_trace.resolved_constraints.maximum_price == 120,
            ),
            (
                "activity_retained",
                final_trace.resolved_constraints.activity
                == first_trace.resolved_constraints.activity,
            ),
            (
                "turn_1_maximum_price_change",
                "maximum_price"
                in [change.field for change in first_trace.constraint_changes],
            ),
            (
                "turn_2_colour_change",
                "colour"
                in [change.field for change in second_trace.constraint_changes],
            ),
            (
                "turn_3_maximum_price_change",
                "maximum_price"
                in [change.field for change in final_trace.constraint_changes],
            ),
            ("turn_3_tool_calls", bool(final_trace.tool_calls)),
            ("turn_3_recommendations", bool(recommendation_ids)),
            (
                "turn_3_recommendations_match_trace",
                recommendation_ids == final_trace.recommended_product_ids,
            ),
            (
                "turn_3_validate_discount",
                "validate_discount"
                in [tool_call.tool_name for tool_call in final_trace.tool_calls],
            ),
            (
                "turn_3_active_promotion",
                final_response.promotion is not None
                and final_response.promotion.code == "WELCOME10"
                and final_response.promotion.valid
                and final_response.promotion.reason == "active",
            ),
            (
                "turn_3_pricing_consistent",
                _pricing_is_consistent(final_response, final_trace),
            ),
        )
        if not passed
    ]
    if failed_checks:
        print("Live smoke completed without required Phase 7 state/evidence.")
        _print_safe_failure_diagnostics(traces, recommendation_ids, failed_checks)
        return 1

    print(f"model: {final_trace.model}")
    print(f"prompt_version: {final_trace.prompt_version}")
    print("turn_indices: 1,2,3")
    for trace in traces:
        changed_fields = ",".join(change.field for change in trace.constraint_changes)
        print(f"turn_{trace.turn_index}_changed_fields: {changed_fields}")
    print(f"tool_calls: {sum(len(trace.tool_calls) for trace in traces)}")
    print(f"recommendations: {len(recommendation_ids)}")
    print(f"recommendation_ids: {','.join(recommendation_ids)}")
    assert final_response.promotion is not None
    assert final_response.pricing is not None
    print(f"promotion_code: {final_response.promotion.code}")
    print(f"promotion_valid: {str(final_response.promotion.valid).lower()}")
    print(f"promotion_reason: {final_response.promotion.reason}")
    print(f"pricing_product_id: {final_response.pricing.product_id}")
    print("pricing_consistent: true")
    print(f"total_tokens: {sum(trace.token_usage.total_tokens for trace in traces)}")
    print(f"latency_ms: {sum(trace.latency_ms for trace in traces)}")
    return 0


def main() -> int:
    """Run one bounded live scenario and print only safe trace summaries."""
    try:
        settings = Settings.from_environment()
    except ValueError:
        print("Live smoke configuration is invalid.")
        return 2
    if settings.openai_api_key is None:
        print("OPENAI_API_KEY is required for the optional live smoke check.")
        return 2
    return run_live_smoke(settings)


if __name__ == "__main__":
    raise SystemExit(main())
