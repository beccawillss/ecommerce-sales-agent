"""Tests for the strict internal final model-output contract."""

from collections.abc import Callable
from copy import deepcopy

import pytest
from pydantic import ValidationError

from salesagent.agent.final_output import (
    AgentFinalOutput,
    ConstraintUpdates,
    MoneyTextUpdate,
    TextListUpdate,
    TextUpdate,
    final_output_text_format,
)


def valid_payload() -> dict[str, object]:
    return {
        "message": "Ready",
        "nominated_product_ids": [],
        "constraint_updates": ConstraintUpdates.retain_all().model_dump(mode="json"),
    }


def test_final_output_accepts_retain_all_and_field_specific_updates() -> None:
    empty = AgentFinalOutput.model_validate(
        {
            **valid_payload(),
            "message": "  Which activity?  ",
        }
    )
    changed = AgentFinalOutput(
        message="These fit best.",
        nominated_product_ids=(" JKT-003 ", "JKT-001", "JKT-004"),
        constraint_updates=ConstraintUpdates(
            category=TextUpdate(operation="set", value=" Jackets "),
            activity=None,
            weather=TextListUpdate(operation="set", value=("waterproof", "windproof")),
            features=None,
            maximum_price=MoneyTextUpdate(operation="set", value="120.00"),
            colour=TextUpdate(operation="clear", value=None),
            size=None,
            season=None,
            priority=None,
        ),
    )

    assert empty.message == "Which activity?"
    assert empty.constraint_updates == ConstraintUpdates.retain_all()
    assert changed.nominated_product_ids == ("JKT-003", "JKT-001", "JKT-004")
    assert changed.constraint_updates.category is not None
    assert changed.constraint_updates.category.value == "Jackets"
    assert changed.constraint_updates.maximum_price is not None
    assert changed.constraint_updates.maximum_price.value == "120.00"


@pytest.mark.parametrize(
    "updates",
    [
        {"category": {"operation": "set", "value": None}},
        {"category": {"operation": "clear", "value": "jacket"}},
        {"category": {"operation": "replace", "value": "jacket"}},
        {"category": {"operation": "set", "value": "   "}},
        {"weather": {"operation": "set", "value": []}},
        {"weather": {"operation": "set", "value": ["rain", " "]}},
        {"weather": {"operation": "clear", "value": ["rain"]}},
        {"maximum_price": {"operation": "set", "value": "nope"}},
        {"maximum_price": {"operation": "set", "value": "-1"}},
        {"maximum_price": {"operation": "set", "value": "NaN"}},
        {"maximum_price": {"operation": "set", "value": "Infinity"}},
        {"maximum_price": {"operation": "clear", "value": "0"}},
        {"maximum_price": {"operation": "set", "value": None}},
        {"colour": {"operation": "clear", "value": None, "extra": True}},
    ],
)
def test_final_output_rejects_invalid_patch_semantics(
    updates: dict[str, object],
) -> None:
    payload = valid_payload()
    patch = deepcopy(payload["constraint_updates"])
    assert isinstance(patch, dict)
    patch.update(updates)
    payload["constraint_updates"] = patch

    with pytest.raises(ValidationError):
        AgentFinalOutput.model_validate(payload)


def _remove_message(payload: dict[str, object]) -> None:
    payload.pop("message")


def _remove_updates(payload: dict[str, object]) -> None:
    payload.pop("constraint_updates")


def _remove_priority(payload: dict[str, object]) -> None:
    updates = payload["constraint_updates"]
    assert isinstance(updates, dict)
    updates.pop("priority")


def _add_unknown_constraint(payload: dict[str, object]) -> None:
    updates = payload["constraint_updates"]
    assert isinstance(updates, dict)
    updates["product_id"] = None


@pytest.mark.parametrize(
    "mutate",
    [
        lambda payload: payload.update(message=" "),
        lambda payload: payload.update(nominated_product_ids=[" "]),
        lambda payload: payload.update(nominated_product_ids=[123]),
        lambda payload: payload.update(nominated_product_ids=["A", "B", "C", "D"]),
        lambda payload: payload.update(price="1.00"),
        _remove_message,
        _remove_updates,
        _remove_priority,
        _add_unknown_constraint,
    ],
)
def test_final_output_rejects_invalid_or_incomplete_payloads(
    mutate: Callable[[dict[str, object]], None],
) -> None:
    payload = valid_payload()
    mutate(payload)

    with pytest.raises(ValidationError):
        AgentFinalOutput.model_validate(payload)


def test_final_output_text_format_is_fresh_and_strict_at_every_object() -> None:
    first = final_output_text_format()
    second = final_output_text_format()

    assert first is not second
    assert first["type"] == "json_schema"
    assert first["name"] == "agent_final_output"
    assert first["strict"] is True
    schema = first["schema"]
    assert isinstance(schema, dict)
    assert "anyOf" not in schema
    assert set(schema["required"]) == {
        "message",
        "nominated_product_ids",
        "constraint_updates",
    }

    def assert_strict_objects(value: object) -> None:
        if isinstance(value, dict):
            if value.get("type") == "object":
                assert value["additionalProperties"] is False
                assert set(value["required"]) == set(value.get("properties", {}))
            for child in value.values():
                assert_strict_objects(child)
        elif isinstance(value, list):
            for child in value:
                assert_strict_objects(child)

    assert_strict_objects(schema)
    constraint_ref = schema["properties"]["constraint_updates"]["$ref"]
    assert constraint_ref == "#/$defs/ConstraintUpdates"
    constraint_schema = schema["$defs"]["ConstraintUpdates"]
    assert set(constraint_schema["required"]) == {
        "category",
        "activity",
        "weather",
        "features",
        "maximum_price",
        "colour",
        "size",
        "season",
        "priority",
    }
    money_schema = schema["$defs"]["MoneyTextUpdate"]["properties"]["value"]
    assert {branch.get("type") for branch in money_schema["anyOf"]} == {
        "string",
        "null",
    }

    schema["required"].append("mutated")
    assert "mutated" not in second["schema"]["required"]
