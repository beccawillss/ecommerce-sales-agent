"""Explicit, optional live smoke check for the Phase 5 recommendation path."""

from typing import cast

from salesagent.agent.responses_client import ResponsesClient
from salesagent.api.models import ChatRequest
from salesagent.config import Settings
from salesagent.main import create_app
from salesagent.repositories.traces import InMemoryTraceRepository
from salesagent.services.chat import ChatService, ChatServiceError

SMOKE_MESSAGE = "Recommend one waterproof hiking jacket under £160."


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
        response = chat_service.chat(ChatRequest(message=SMOKE_MESSAGE))
    except ChatServiceError as error:
        print("Live smoke failed safely.")
        print(f"failure_category: {error.code}")
        return 1
    except Exception:
        # Never let an unexpected provider or SDK error become terminal output.
        print("Live smoke failed safely before a classified diagnostic was available.")
        return 1

    trace = trace_repository.get(response.trace_id)
    if trace is None:
        print("Live chat succeeded, but its safe trace could not be retrieved.")
        return 1

    recommendation_ids = [item.product_id for item in response.recommendations]
    if (
        not trace.tool_calls
        or not recommendation_ids
        or recommendation_ids != trace.recommended_product_ids
    ):
        print("Live smoke completed without required recommendation evidence.")
        return 1

    print(f"model: {trace.model}")
    print(f"tool_calls: {len(trace.tool_calls)}")
    print(f"recommendations: {len(recommendation_ids)}")
    print(f"recommendation_ids: {','.join(recommendation_ids)}")
    print(f"total_tokens: {trace.token_usage.total_tokens}")
    print(f"latency_ms: {trace.latency_ms}")
    return 0


def main() -> int:
    """Run one bounded live chat and print only safe response/trace summaries."""
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
