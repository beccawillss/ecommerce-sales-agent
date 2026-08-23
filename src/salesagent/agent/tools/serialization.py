"""One explicit JSON serialization strategy for tool-layer models."""

from typing import cast

from pydantic import BaseModel


def serialize_model(model: BaseModel) -> dict[str, object]:
    """Convert a Pydantic model to values accepted by standard JSON tooling."""
    return cast(dict[str, object], model.model_dump(mode="json"))
