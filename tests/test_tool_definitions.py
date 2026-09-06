"""Tests for the authoritative V1 tool registry and strict schemas."""

import json
from decimal import Decimal

import pytest
from pydantic import ValidationError

from salesagent.agent.tools.definitions import TOOL_REGISTRY, tool_definitions
from salesagent.agent.tools.models import SearchProductsArguments

EXPECTED_TOOL_NAMES = {
    "search_products",
    "get_product",
    "check_inventory",
    "validate_discount",
}


def test_registry_exposes_exactly_four_unique_v1_tools() -> None:
    names = [spec.name for spec in TOOL_REGISTRY]

    assert len(names) == 4
    assert len(names) == len(set(names))
    assert set(names) == EXPECTED_TOOL_NAMES


def test_definitions_are_strict_json_serializable_function_tools() -> None:
    definitions = tool_definitions()

    json.dumps(definitions)
    assert {definition["name"] for definition in definitions} == EXPECTED_TOOL_NAMES
    for definition in definitions:
        assert definition["type"] == "function"
        assert definition["strict"] is True
        assert isinstance(definition["description"], str)

        parameters = definition["parameters"]
        assert isinstance(parameters, dict)
        assert parameters["type"] == "object"
        assert parameters["additionalProperties"] is False
        assert set(parameters["required"]) == set(parameters["properties"])


def test_registry_argument_models_reject_unexpected_properties() -> None:
    for spec in TOOL_REGISTRY:
        try:
            spec.argument_model.model_validate({"unexpected": "value"})
        except ValidationError:
            continue
        raise AssertionError(f"{spec.name} accepted an unexpected property")


def test_search_schema_declares_all_supported_phase_one_filters() -> None:
    definition = next(
        item for item in tool_definitions() if item["name"] == "search_products"
    )
    parameters = definition["parameters"]
    assert isinstance(parameters, dict)

    assert set(parameters["properties"]) == {
        "category",
        "activity",
        "weather",
        "features",
        "maximum_price",
        "colour",
        "size",
        "in_stock_only",
    }


def test_search_description_explains_exact_catalogue_filter_boundary() -> None:
    definition = next(
        item for item in tool_definitions() if item["name"] == "search_products"
    )
    description = definition["description"]

    assert isinstance(description, str)
    assert "exact case-insensitive catalogue labels" in description
    assert "Omit an uncertain broader term" in description
    assert "inspect the returned product and variant facts" in description


def test_search_maximum_price_has_openai_compatible_nullable_string_schema() -> None:
    definition = next(
        item for item in tool_definitions() if item["name"] == "search_products"
    )
    parameters = definition["parameters"]
    assert isinstance(parameters, dict)
    properties = parameters["properties"]
    assert isinstance(properties, dict)

    maximum_price = properties["maximum_price"]
    assert maximum_price == {
        "type": ["string", "null"],
        "description": (
            "Maximum price in GBP as a decimal amount, for example '160.00'. "
            "Use null when there is no price limit."
        ),
    }
    assert "pattern" not in json.dumps(maximum_price)
    assert "anyOf" not in json.dumps(maximum_price)


def test_search_maximum_price_string_validates_to_decimal() -> None:
    arguments = SearchProductsArguments.model_validate({"maximum_price": "160.00"})

    assert arguments.maximum_price == Decimal("160.00")
    assert isinstance(arguments.maximum_price, Decimal)


def test_search_maximum_price_null_means_no_limit() -> None:
    arguments = SearchProductsArguments.model_validate({"maximum_price": None})

    assert arguments.maximum_price is None


@pytest.mark.parametrize("maximum_price", ["not-a-price", "-0.01"])
def test_search_maximum_price_rejects_malformed_or_negative_strings(
    maximum_price: str,
) -> None:
    with pytest.raises(ValidationError):
        SearchProductsArguments.model_validate({"maximum_price": maximum_price})
