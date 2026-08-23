"""Shopper-facing chat route."""

from fastapi import APIRouter

from salesagent.api.models import ChatRequest, ChatResponse
from salesagent.services.chat import ChatService


def create_chat_router(chat_service: ChatService) -> APIRouter:
    """Build a chat router bound to an explicit application service."""
    router = APIRouter(prefix="/api/v1/chat", tags=["chat"])

    @router.post(
        "",
        operation_id="chat",
        response_model=ChatResponse,
        responses={
            400: {"description": "Invalid request"},
            422: {"description": "Schema validation failure"},
            500: {"description": "Unexpected server error"},
        },
    )
    def chat(request: ChatRequest) -> ChatResponse:
        return chat_service.chat(request)

    return router
