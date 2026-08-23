"""FastAPI application entry point."""

from typing import Literal

from fastapi import FastAPI
from pydantic import BaseModel

from salesagent.api.routes.chat import create_chat_router
from salesagent.api.routes.traces import create_trace_router
from salesagent.config import Settings
from salesagent.repositories.traces import InMemoryTraceRepository
from salesagent.services.chat import ChatService


class HealthResponse(BaseModel):
    """Response returned by the health endpoint."""

    status: Literal["ok"]


def health() -> HealthResponse:
    """Report that the application is running."""
    return HealthResponse(status="ok")


def create_app(settings: Settings | None = None) -> FastAPI:
    """Assemble an application with isolated in-memory Phase 2 state."""
    settings = settings or Settings.from_environment()
    trace_repository = InMemoryTraceRepository()
    chat_service = ChatService(trace_repository)

    application = FastAPI(title="Sales Agent", version="1.0.0")
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
