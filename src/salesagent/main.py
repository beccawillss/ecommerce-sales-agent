"""FastAPI application entry point."""

from typing import Literal

from fastapi import FastAPI
from pydantic import BaseModel


class HealthResponse(BaseModel):
    """Response returned by the health endpoint."""

    status: Literal["ok"]


app = FastAPI(title="Sales Agent")


@app.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    """Report that the application is running."""
    return HealthResponse(status="ok")
