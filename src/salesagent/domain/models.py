"""Authoritative, immutable commerce domain models."""

from decimal import Decimal
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

Money = Annotated[
    Decimal,
    Field(ge=Decimal("0.00"), decimal_places=2, allow_inf_nan=False),
]
Percentage = Annotated[
    Decimal,
    Field(ge=Decimal("0"), le=Decimal("100"), allow_inf_nan=False),
]


class CommerceModel(BaseModel):
    """Base configuration shared by immutable commerce values."""

    model_config = ConfigDict(extra="forbid", frozen=True)


class ProductVariant(CommerceModel):
    """Stock for one exact product colour and size combination."""

    colour: str = Field(min_length=1)
    size: str = Field(min_length=1)
    stock: int = Field(ge=0)

    @field_validator("colour", "size")
    @classmethod
    def strip_variant_values(cls, value: str) -> str:
        """Reject values that contain only whitespace."""
        value = value.strip()
        if not value:
            raise ValueError("variant values must not be blank")
        return value


class Product(CommerceModel):
    """A catalogue product whose facts originate in the product repository."""

    id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    category: str = Field(min_length=1)
    price: Money
    currency: Literal["GBP"]
    product_url: str = Field(pattern=r"^/products/[a-z0-9-]+$")
    activities: tuple[str, ...] = Field(min_length=1)
    weather: tuple[str, ...] = Field(min_length=1)
    features: tuple[str, ...] = Field(min_length=1)
    waterproof_rating: Literal["none", "water-resistant", "moderate", "high"]
    warmth: Literal["none", "light", "medium", "high", "shell"]
    season: tuple[Literal["spring", "summer", "autumn", "winter"], ...] = Field(
        min_length=1
    )
    variants: tuple[ProductVariant, ...] = Field(min_length=1)

    @field_validator("id", "name", "category", "product_url")
    @classmethod
    def strip_product_values(cls, value: str) -> str:
        """Remove insignificant boundary whitespace from product facts."""
        value = value.strip()
        if not value:
            raise ValueError("product values must not be blank")
        return value

    @field_validator("activities", "weather", "features")
    @classmethod
    def validate_tags(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        """Require non-empty, unique tags while preserving catalogue spelling."""
        cleaned = tuple(value.strip() for value in values)
        if any(not value for value in cleaned):
            raise ValueError("product tags must not be blank")
        if len({value.casefold() for value in cleaned}) != len(cleaned):
            raise ValueError("product tags must be unique")
        return cleaned

    @model_validator(mode="after")
    def variants_are_unique(self) -> "Product":
        """Prevent ambiguous stock records for the same exact variant."""
        keys = {
            (variant.colour.casefold(), variant.size.casefold())
            for variant in self.variants
        }
        if len(keys) != len(self.variants):
            raise ValueError("product variants must have unique colour and size pairs")
        return self

    @property
    def total_stock(self) -> int:
        """Return authoritative product stock summed across all variants."""
        return sum(variant.stock for variant in self.variants)


class Promotion(CommerceModel):
    """A promotion definition loaded from the promotion repository."""

    code: str = Field(min_length=1)
    discount_percent: Percentage
    active: bool

    @field_validator("code")
    @classmethod
    def normalise_code(cls, value: str) -> str:
        """Store promotion codes in their canonical uppercase form."""
        value = value.strip().upper()
        if not value:
            raise ValueError("promotion code must not be blank")
        return value


class ProductSearchCriteria(CommerceModel):
    """Optional filters that are combined to narrow catalogue candidates."""

    category: str | None = None
    activity: str | None = None
    weather: tuple[str, ...] = ()
    features: tuple[str, ...] = ()
    maximum_price: Money | None = None
    colour: str | None = None
    size: str | None = None
    in_stock_only: bool = False

    @field_validator("category", "activity", "colour", "size")
    @classmethod
    def validate_optional_text(cls, value: str | None) -> str | None:
        """Normalise boundary whitespace and reject blank active filters."""
        if value is None:
            return None
        value = value.strip()
        if not value:
            raise ValueError("search text must not be blank")
        return value

    @field_validator("weather", "features")
    @classmethod
    def validate_filter_tags(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        """Reject blank filter tags so constraints cannot be silently ignored."""
        cleaned = tuple(value.strip() for value in values)
        if any(not value for value in cleaned):
            raise ValueError("search tags must not be blank")
        return cleaned


class InventoryResult(CommerceModel):
    """Explicit outcome for one exact product variant inventory lookup."""

    product_id: str
    colour: str
    size: str
    stock: int | None = Field(default=None, ge=0)
    available: bool
    status: Literal[
        "in_stock", "out_of_stock", "variant_not_found", "product_not_found"
    ]


class DiscountValidationResult(CommerceModel):
    """Explicit outcome from validating a submitted promotion code."""

    code: str = Field(min_length=1)
    valid: bool
    discount_percent: Percentage | None = None
    reason: Literal["active", "inactive", "unknown_code"]

    @field_validator("code")
    @classmethod
    def normalise_result_code(cls, value: str) -> str:
        """Retain one canonical comparison/display form for validated codes."""
        value = value.strip().upper()
        if not value:
            raise ValueError("promotion code must not be blank")
        return value

    @model_validator(mode="after")
    def result_is_semantically_consistent(self) -> "DiscountValidationResult":
        """Reject evidence whose validity, reason, and percentage disagree."""
        if self.valid and self.reason == "active" and self.discount_percent is not None:
            return self
        if (
            not self.valid
            and self.reason in {"inactive", "unknown_code"}
            and self.discount_percent is None
        ):
            return self
        raise ValueError("discount validation result is inconsistent")
