"""Strict application-owned contract for a model's final shopper response."""

from copy import deepcopy
from typing import Annotated, cast

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

NonBlankText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


class AgentFinalOutput(BaseModel):
    """Untrusted prose and product-ID nominations returned by the model."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    message: NonBlankText
    nominated_product_ids: tuple[NonBlankText, ...] = Field(max_length=3)


def final_output_text_format() -> dict[str, object]:
    """Return a fresh strict Responses ``text.format`` definition."""
    schema = deepcopy(AgentFinalOutput.model_json_schema(mode="validation"))
    schema.pop("title", None)
    properties = cast(dict[str, object], schema.get("properties", {}))
    for property_schema in properties.values():
        if isinstance(property_schema, dict):
            property_schema.pop("title", None)

    return {
        "type": "json_schema",
        "name": "agent_final_output",
        "description": "Final shopper-facing message and grounded product nominations.",
        "strict": True,
        "schema": schema,
    }
