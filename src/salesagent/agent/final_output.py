"""Strict application-owned contract for a model's final shopper response."""

from copy import deepcopy
from decimal import Decimal, InvalidOperation
from typing import Annotated, Literal, Self, cast

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

NonBlankText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


class StrictOutputModel(BaseModel):
    """Immutable strict base for every model-authored output object."""

    model_config = ConfigDict(extra="forbid", frozen=True)


class TextUpdate(StrictOutputModel):
    """Set or clear one scalar shopper constraint."""

    operation: Literal["set", "clear"]
    value: NonBlankText | None

    @model_validator(mode="after")
    def validate_operation_value(self) -> Self:
        if self.operation == "set" and self.value is not None:
            return self
        if self.operation == "clear" and self.value is None:
            return self
        raise ValueError("set requires a value and clear requires null")


class TextListUpdate(StrictOutputModel):
    """Replace or clear one complete list-valued shopper constraint."""

    operation: Literal["set", "clear"]
    value: tuple[NonBlankText, ...] | None

    @model_validator(mode="after")
    def validate_operation_value(self) -> Self:
        if self.operation == "set" and self.value:
            return self
        if self.operation == "clear" and self.value is None:
            return self
        raise ValueError("set requires a non-empty list and clear requires null")


class MoneyTextUpdate(StrictOutputModel):
    """Set or clear a Decimal-safe maximum-price constraint."""

    operation: Literal["set", "clear"]
    value: NonBlankText | None

    @model_validator(mode="after")
    def validate_operation_value(self) -> Self:
        if self.operation == "clear" and self.value is None:
            return self
        if self.operation != "set" or self.value is None:
            raise ValueError("set requires a value and clear requires null")
        try:
            amount = Decimal(self.value)
        except InvalidOperation as error:
            raise ValueError("maximum price must be a decimal string") from error
        if not amount.is_finite() or amount < 0:
            raise ValueError("maximum price must be finite and nonnegative")
        return self


class ConstraintUpdates(StrictOutputModel):
    """Fixed-field patch; null means retain the existing field value."""

    category: TextUpdate | None
    activity: TextUpdate | None
    weather: TextListUpdate | None
    features: TextListUpdate | None
    maximum_price: MoneyTextUpdate | None
    colour: TextUpdate | None
    size: TextUpdate | None
    season: TextUpdate | None
    priority: TextUpdate | None

    @classmethod
    def retain_all(cls) -> Self:
        """Build the explicit no-change patch required by strict output."""
        return cls(
            category=None,
            activity=None,
            weather=None,
            features=None,
            maximum_price=None,
            colour=None,
            size=None,
            season=None,
            priority=None,
        )


class AgentFinalOutput(StrictOutputModel):
    """Untrusted prose and commerce nominations returned by the model."""

    message: NonBlankText
    nominated_product_ids: tuple[NonBlankText, ...] = Field(max_length=3)
    nominated_promotion_code: NonBlankText | None
    constraint_updates: ConstraintUpdates


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
        "description": (
            "Final shopper-facing message, grounded product and promotion "
            "nominations, and explicit shopper-constraint updates."
        ),
        "strict": True,
        "schema": schema,
    }
