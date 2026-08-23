"""Pydantic models matching the public V1 API contract."""

from datetime import datetime
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    PlainSerializer,
    WithJsonSchema,
    field_validator,
)

ApiMoney = Annotated[
    Decimal,
    Field(ge=Decimal("0"), allow_inf_nan=False),
    PlainSerializer(float, return_type=float, when_used="json"),
    WithJsonSchema({"type": "number", "minimum": 0}),
]
ApiPercentage = Annotated[
    Decimal,
    Field(ge=Decimal("0"), le=Decimal("100"), allow_inf_nan=False),
    PlainSerializer(float, return_type=float, when_used="json"),
    WithJsonSchema({"type": "number", "minimum": 0, "maximum": 100}),
]


class ApiModel(BaseModel):
    """Reject fields outside the authoritative API contract."""

    model_config = ConfigDict(extra="forbid")


class ChatRequest(ApiModel):
    """One shopper message and an optional existing session identifier."""

    session_id: str | None = Field(default=None, min_length=1)
    message: str = Field(min_length=1, max_length=4000)

    @field_validator("message")
    @classmethod
    def reject_blank_message(cls, value: str) -> str:
        """Reject whitespace-only messages without altering recorded input."""
        if not value.strip():
            raise ValueError("message must not be blank")
        return value


class VariantAvailability(ApiModel):
    """Customer-facing availability for one exact product variant."""

    colour: str
    size: str
    stock: int = Field(ge=0)


class ProductRecommendation(ApiModel):
    """Structured product recommendation at the HTTP boundary."""

    product_id: str
    name: str
    price: ApiMoney
    currency: Literal["GBP"]
    product_url: str
    availability: Literal["in_stock", "out_of_stock", "partial", "unknown"]
    matched_variant: VariantAvailability | None = None


class PromotionResult(ApiModel):
    """Promotion validation details exposed by the API contract."""

    code: str
    valid: bool
    discount_percent: ApiPercentage | None = None
    reason: str | None = None


class PricingResult(ApiModel):
    """Authoritative pricing details exposed by the API contract."""

    product_id: str
    base_price: ApiMoney
    final_price: ApiMoney
    currency: Literal["GBP"]
    discount_code: str | None = None
    discount_percent: ApiPercentage | None = None


class ChatResponse(ApiModel):
    """Structured response for one completed chat turn."""

    session_id: str
    trace_id: str
    message: str
    recommendations: list[ProductRecommendation] = Field(max_length=3)
    promotion: PromotionResult | None = None
    pricing: PricingResult | None = None


class ResolvedConstraints(ApiModel):
    """Normalized shopper constraints known after a chat turn."""

    category: str | None = None
    activity: str | None = None
    weather: list[str] = Field(default_factory=list)
    features: list[str] = Field(default_factory=list)
    maximum_price: ApiMoney | None = None
    colour: str | None = None
    size: str | None = None
    season: str | None = None
    priority: str | None = None


class ConstraintChange(ApiModel):
    """One change to a resolved shopper constraint."""

    field: str
    previous: object
    current: object


class ToolCallTrace(ApiModel):
    """Trace record for one schema-validated commerce tool call."""

    sequence: int = Field(ge=1)
    tool_call_id: str
    tool_name: Literal[
        "search_products", "get_product", "check_inventory", "validate_discount"
    ]
    arguments: dict[str, object]
    result: dict[str, object]
    status: Literal["success", "error"]
    duration_ms: int = Field(ge=0)


class RecommendationValidation(ApiModel):
    """Checks applied to structured recommendations for a turn."""

    all_products_exist: bool
    prices_match_catalogue: bool
    urls_match_catalogue: bool
    stock_claims_validated: bool
    validation_errors: list[str] = Field(default_factory=list)


class TokenUsage(ApiModel):
    """Model token usage recorded for a chat turn."""

    input_tokens: int = Field(ge=0)
    output_tokens: int = Field(ge=0)
    total_tokens: int = Field(ge=0)


class TraceError(ApiModel):
    """Safe structured error included in an evaluation trace."""

    code: str
    message: str
    tool_call_id: str | None = None


class TraceResponse(ApiModel):
    """Inspectable execution trace for one completed chat turn."""

    trace_id: str
    session_id: str
    timestamp: datetime
    turn_index: int = Field(ge=1)
    user_message: str
    model: str
    prompt_version: str
    resolved_constraints: ResolvedConstraints
    constraint_changes: list[ConstraintChange]
    tool_calls: list[ToolCallTrace]
    recommendation_validation: RecommendationValidation
    recommended_product_ids: list[str]
    promotion: PromotionResult | None = None
    pricing: PricingResult | None = None
    latency_ms: int = Field(ge=0)
    token_usage: TokenUsage
    errors: list[TraceError]
