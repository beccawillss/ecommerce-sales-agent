"""Evaluation-only trace route."""

from typing import Annotated

from fastapi import APIRouter, HTTPException, Path, status

from salesagent.api.models import TraceResponse
from salesagent.repositories.traces import InMemoryTraceRepository


def create_trace_router(trace_repository: InMemoryTraceRepository) -> APIRouter:
    """Build a trace router bound to an explicit repository instance."""
    router = APIRouter(prefix="/api/v1/traces", tags=["evaluation"])

    @router.get(
        "/{trace_id}",
        operation_id="getTrace",
        response_model=TraceResponse,
        responses={404: {"description": "Trace not found"}},
    )
    def get_trace(
        trace_id: Annotated[str, Path(min_length=1)],
    ) -> TraceResponse:
        trace = trace_repository.get(trace_id)
        if trace is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Trace not found",
            )
        return trace

    return router
