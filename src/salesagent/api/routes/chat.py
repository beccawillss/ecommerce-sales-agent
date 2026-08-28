"""Shopper-facing chat route."""

from fastapi import APIRouter, HTTPException, status

from salesagent.api.models import ChatRequest, ChatResponse
from salesagent.services.chat import (
    GENERIC_FAILURE_DETAIL,
    ChatService,
    ChatServiceError,
)


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
        try:
            return chat_service.chat(request)
        except ChatServiceError as error:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=GENERIC_FAILURE_DETAIL,
            ) from error

    return router
