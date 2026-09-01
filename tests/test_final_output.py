"""Tests for the strict internal final model-output contract."""

import pytest
from pydantic import ValidationError

from salesagent.agent.final_output import AgentFinalOutput, final_output_text_format


def test_final_output_accepts_empty_and_three_nominations() -> None:
    empty = AgentFinalOutput.model_validate(
        {"message": "  Which activity?  ", "nominated_product_ids": []}
    )
    three = AgentFinalOutput.model_validate(
        {
            "message": "These fit best.",
            "nominated_product_ids": [" JKT-003 ", "JKT-001", "JKT-004"],
        }
    )

    assert empty.message == "Which activity?"
    assert empty.nominated_product_ids == ()
    assert three.nominated_product_ids == ("JKT-003", "JKT-001", "JKT-004")


@pytest.mark.parametrize(
    "payload",
    [
        {"message": " ", "nominated_product_ids": []},
        {"message": "Ready", "nominated_product_ids": [" "]},
        {"message": "Ready", "nominated_product_ids": [123]},
        {
            "message": "Ready",
            "nominated_product_ids": ["A", "B", "C", "D"],
        },
        {"message": "Ready", "nominated_product_ids": [], "price": "1.00"},
        {"message": "Ready"},
    ],
)
def test_final_output_rejects_invalid_payloads(payload: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        AgentFinalOutput.model_validate(payload)


def test_final_output_text_format_is_strict_fresh_and_minimal() -> None:
    first = final_output_text_format()
    second = final_output_text_format()

    assert first is not second
    assert first["type"] == "json_schema"
    assert first["name"] == "agent_final_output"
    assert first["strict"] is True
    schema = first["schema"]
    assert isinstance(schema, dict)
    assert set(schema["required"]) == {"message", "nominated_product_ids"}
    assert schema["additionalProperties"] is False
    nominations = schema["properties"]["nominated_product_ids"]
    assert nominations["type"] == "array"
    assert nominations["maxItems"] == 3

    schema["required"].append("mutated")
    assert "mutated" not in second["schema"]["required"]
