"""Tests for the authoritative V1 tool registry and strict schemas."""

import json

from pydantic import ValidationError

from salesagent.agent.tools.definitions import TOOL_REGISTRY, tool_definitions

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
