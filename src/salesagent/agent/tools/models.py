"""Typed arguments and JSON-facing results for commerce tools."""

from typing import Annotated, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from salesagent.domain.models import (
    DiscountValidationResult,
    InventoryResult,
    Product,
    ProductSearchCriteria,
    ProductVariant,
)

NonBlankText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


class ToolArguments(BaseModel):
    """Strict base for arguments supplied by an external orchestrator."""

    model_config = ConfigDict(extra="forbid", frozen=True)


class SearchProductsArguments(ProductSearchCriteria):
    """Arguments for the existing deterministic product search criteria."""


class GetProductArguments(ToolArguments):
    """Arguments for retrieving one product by stable ID."""

    product_id: NonBlankText


class CheckInventoryArguments(ToolArguments):
    """Arguments for checking one exact colour and size variant."""

    product_id: NonBlankText
    colour: NonBlankText
    size: NonBlankText


class ValidateDiscountArguments(ToolArguments):
    """Arguments for validating one promotion code."""

    code: NonBlankText


class ToolResultModel(BaseModel):
    """Strict base for stable JSON-facing tool results."""

    model_config = ConfigDict(extra="forbid", frozen=True)


class ProductVariantData(ToolResultModel):
    """Exact variant facts returned to future orchestration."""

    colour: str
    size: str
    stock: int = Field(ge=0)

    @classmethod
    def from_domain(cls, variant: ProductVariant) -> Self:
        return cls(colour=variant.colour, size=variant.size, stock=variant.stock)


class ProductData(ToolResultModel):
    """Explicit authoritative product facts exposed by commerce tools."""

    product_id: str
    name: str
    category: str
    price: str
    currency: Literal["GBP"]
    product_url: str
    activities: tuple[str, ...]
    weather: tuple[str, ...]
    features: tuple[str, ...]
    waterproof_rating: str
    warmth: str
    season: tuple[str, ...]
    variants: tuple[ProductVariantData, ...]
    total_stock: int = Field(ge=0)

    @classmethod
    def from_domain(cls, product: Product) -> Self:
        """Map an authoritative product without exposing its internal model."""
        return cls(
            product_id=product.id,
            name=product.name,
            category=product.category,
            price=format(product.price, "f"),
            currency=product.currency,
            product_url=product.product_url,
            activities=product.activities,
            weather=product.weather,
            features=product.features,
            waterproof_rating=product.waterproof_rating,
            warmth=product.warmth,
            season=product.season,
            variants=tuple(
                ProductVariantData.from_domain(variant) for variant in product.variants
            ),
            total_stock=product.total_stock,
        )


class SearchProductsData(ToolResultModel):
    """Deterministically ordered product candidates."""

    products: tuple[ProductData, ...]
    count: int = Field(ge=0)


class InventoryData(ToolResultModel):
    """Exact inventory outcome returned by the commerce service."""

    product_id: str
    colour: str
    size: str
    stock: int | None = Field(default=None, ge=0)
    available: bool
    status: Literal[
        "in_stock", "out_of_stock", "variant_not_found", "product_not_found"
    ]

    @classmethod
    def from_domain(cls, result: InventoryResult) -> Self:
        return cls.model_validate(result.model_dump())


class DiscountData(ToolResultModel):
    """Promotion validation outcome returned by the commerce service."""

    code: str
    valid: bool
    discount_percent: str | None = None
    reason: Literal["active", "inactive", "unknown_code"]

    @classmethod
    def from_domain(cls, result: DiscountValidationResult) -> Self:
        percentage = result.discount_percent
        return cls(
            code=result.code,
            valid=result.valid,
            discount_percent=format(percentage, "f")
            if percentage is not None
            else None,
            reason=result.reason,
        )


class ToolExecutionError(ToolResultModel):
    """Safe, stable dispatcher failure information."""

    code: Literal[
        "unknown_tool", "invalid_arguments", "product_not_found", "execution_error"
    ]
    message: str


class ToolExecutionResult(ToolResultModel):
    """Stable envelope for every dispatcher execution attempt."""

    tool_name: str
    success: bool
    arguments: dict[str, object] | None
    data: dict[str, object] | None
    error: ToolExecutionError | None
    duration_ms: int = Field(ge=0)
