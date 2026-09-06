"""Authoritative registry and strict JSON schemas for the four V1 tools."""

from copy import deepcopy
from dataclasses import dataclass
from typing import Literal, cast

from pydantic import BaseModel

from salesagent.agent.tools.models import (
    CheckInventoryArguments,
    GetProductArguments,
    SearchProductsArguments,
    ValidateDiscountArguments,
)

ToolName = Literal[
    "search_products", "get_product", "check_inventory", "validate_discount"
]

_SEARCH_MAXIMUM_PRICE_SCHEMA: dict[str, object] = {
    "type": ["string", "null"],
    "description": (
        "Maximum price in GBP as a decimal amount, for example '160.00'. "
        "Use null when there is no price limit."
    ),
}


@dataclass(frozen=True, slots=True)
class ToolSpec:
    """Definition metadata and argument model for one allowlisted tool."""

    name: ToolName
    description: str
    argument_model: type[BaseModel]


TOOL_REGISTRY: tuple[ToolSpec, ...] = (
    ToolSpec(
        name="search_products",
        description=(
            "Read-only catalogue search using explicit shopper constraints. "
            "Text filters match exact case-insensitive catalogue labels; use one "
            "only when its authoritative label is known. Omit an uncertain broader "
            "term and inspect the returned product and variant facts instead. "
            "Returns all matching catalogue candidates in deterministic price then "
            "product-ID order, including authoritative product IDs and product facts. "
            "Use it to discover candidates; it does not rank or choose recommendations."
        ),
        argument_model=SearchProductsArguments,
    ),
    ToolSpec(
        name="get_product",
        description=(
            "Read-only lookup of authoritative product facts by stable catalogue "
            "product ID, including price, attributes, variants, and product URL. "
            "Use when the product ID is already known."
        ),
        argument_model=GetProductArguments,
    ),
    ToolSpec(
        name="check_inventory",
        description=(
            "Read-only exact variant stock lookup by product ID, colour, and size. "
            "Returns the requested variant's stock count and one of in_stock, "
            "out_of_stock, variant_not_found, or product_not_found. "
            "Never infers availability from another colour or size."
        ),
        argument_model=CheckInventoryArguments,
    ),
    ToolSpec(
        name="validate_discount",
        description=(
            "Read-only promotion-code validation using authoritative promotion data. "
            "Returns whether the code is valid, its discount percentage when valid, "
            "and a reason such as active, inactive, or unknown_code. "
            "Does not apply a discount or calculate a final price."
        ),
        argument_model=ValidateDiscountArguments,
    ),
)

_TOOLS_BY_NAME: dict[str, ToolSpec] = {spec.name: spec for spec in TOOL_REGISTRY}


def get_tool_spec(name: str) -> ToolSpec | None:
    """Return allowlisted metadata for a supported tool name."""
    return _TOOLS_BY_NAME.get(name)


def tool_definitions() -> list[dict[str, object]]:
    """Return fresh JSON-serializable definitions for future function calling."""
    return [
        {
            "type": "function",
            "name": spec.name,
            "description": spec.description,
            "parameters": _strict_parameters(spec.argument_model),
            "strict": True,
        }
        for spec in TOOL_REGISTRY
    ]


def _strict_parameters(argument_model: type[BaseModel]) -> dict[str, object]:
    """Normalize four known Pydantic schemas for strict function calling.

    Strict schemas require every declared property to be listed as required.
    Search fields retain their explicit nullable types or concrete empty/false
    representations, while dispatcher-side Pydantic defaults still make direct
    internal calls ergonomic.
    """
    schema = deepcopy(argument_model.model_json_schema(mode="validation"))
    schema.pop("title", None)
    schema["additionalProperties"] = False
    properties = cast(dict[str, object], schema.get("properties", {}))
    schema["required"] = list(properties)

    for property_schema in properties.values():
        if isinstance(property_schema, dict):
            property_schema.pop("default", None)
            property_schema.pop("title", None)

    if argument_model is SearchProductsArguments:
        properties["maximum_price"] = deepcopy(_SEARCH_MAXIMUM_PRICE_SCHEMA)

    return cast(dict[str, object], schema)
