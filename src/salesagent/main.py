"""FastAPI application entry point."""

from pathlib import Path
from typing import Literal

from fastapi import FastAPI
from pydantic import BaseModel

from salesagent.agent.orchestrator import AgentOrchestrator
from salesagent.agent.responses_client import OpenAIResponsesClient, ResponsesClient
from salesagent.agent.tools.dispatcher import ToolDispatcher
from salesagent.api.routes.chat import create_chat_router
from salesagent.api.routes.traces import create_trace_router
from salesagent.config import Settings
from salesagent.repositories.products import ProductRepository
from salesagent.repositories.promotions import PromotionRepository
from salesagent.repositories.sessions import InMemorySessionRepository
from salesagent.repositories.traces import InMemoryTraceRepository
from salesagent.services.chat import ChatService
from salesagent.services.commerce import CommerceService
from salesagent.services.constraints import ConstraintStateMerger
from salesagent.services.pricing import PromotionPricingService
from salesagent.services.recommendations import RecommendationHydrator

PROJECT_ROOT = Path(__file__).resolve().parents[2]


class HealthResponse(BaseModel):
    """Response returned by the health endpoint."""

    status: Literal["ok"]


def health() -> HealthResponse:
    """Report that the application is running."""
    return HealthResponse(status="ok")


def create_app(
    settings: Settings | None = None,
    *,
    responses_client: ResponsesClient | None = None,
) -> FastAPI:
    """Assemble an application with isolated state and injectable model I/O."""
    settings = settings or Settings.from_environment()
    trace_repository = InMemoryTraceRepository()
    session_repository = InMemorySessionRepository()
    commerce_service = CommerceService(
        products=ProductRepository(PROJECT_ROOT / "data" / "products.json"),
        promotions=PromotionRepository(PROJECT_ROOT / "data" / "discounts.json"),
    )
    dispatcher = ToolDispatcher(commerce_service)
    model_client = (
        responses_client
        if responses_client is not None
        else OpenAIResponsesClient(
            api_key=settings.openai_api_key,
            timeout_seconds=settings.openai_timeout_seconds,
            max_retries=2,
        )
    )
    orchestrator = AgentOrchestrator(
        responses_client=model_client,
        dispatcher=dispatcher,
        model=settings.openai_model,
        reasoning_effort=settings.openai_reasoning_effort,
        max_output_tokens=settings.openai_max_output_tokens,
    )
    chat_service = ChatService(
        trace_repository,
        orchestrator,
        RecommendationHydrator(commerce_service),
        PromotionPricingService(),
        session_repository,
        ConstraintStateMerger(),
    )

    application = FastAPI(title="Sales Agent", version="1.0.0")
    # Developer-side diagnostics can exercise the exact assembled service without
    # widening the shopper-facing HTTP error contract.
    application.state.chat_service = chat_service
    application.state.trace_repository = trace_repository
    application.state.session_repository = session_repository
    application.add_api_route(
        "/health",
        health,
        methods=["GET"],
        response_model=HealthResponse,
    )
    application.include_router(create_chat_router(chat_service))
    if settings.enable_eval_traces:
        application.include_router(create_trace_router(trace_repository))
    return application


app = create_app()
