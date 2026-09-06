"""Deterministic promotion resolution and Decimal-safe GBP pricing."""

from collections.abc import Iterable
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal, DecimalException
from typing import Literal

from salesagent.domain.models import DiscountValidationResult
from salesagent.services.recommendations import HydratedRecommendation

GBP_QUANTUM = Decimal("0.01")
GBP_ROUNDING = ROUND_HALF_UP

PromotionPricingErrorCode = Literal[
    "promotion_nomination_missing",
    "ungrounded_promotion_code",
    "pricing_calculation_failed",
]

_ERROR_MESSAGES: dict[PromotionPricingErrorCode, str] = {
    "promotion_nomination_missing": (
        "Current promotion evidence was not selected by the model."
    ),
    "ungrounded_promotion_code": (
        "The selected promotion lacked current validation evidence."
    ),
    "pricing_calculation_failed": (
        "Authoritative pricing could not be calculated safely."
    ),
}


@dataclass(frozen=True, slots=True)
class CalculatedPrice:
    """One authoritative internal quote, including its audited discount amount."""

    product_id: str
    base_price: Decimal
    discount_amount: Decimal
    final_price: Decimal
    currency: Literal["GBP"]
    discount_code: str
    discount_percent: Decimal


@dataclass(frozen=True, slots=True)
class PromotionPricingError:
    """A fixed safe validation failure suitable for trace mapping."""

    code: PromotionPricingErrorCode
    message: str


@dataclass(frozen=True, slots=True)
class PromotionPricingOutcome:
    """Resolved promotion, optional quote, and safe partial-result evidence."""

    promotion: DiscountValidationResult | None
    pricing: CalculatedPrice | None
    errors: tuple[PromotionPricingError, ...] = ()


class PromotionPricingService:
    """Resolve one grounded promotion and price the first accepted card."""

    def resolve(
        self,
        *,
        nominated_promotion_code: str | None,
        grounded_promotions: Iterable[DiscountValidationResult],
        recommendations: Iterable[HydratedRecommendation],
    ) -> PromotionPricingOutcome:
        """Return only promotion and price data justified by current evidence."""
        evidence = tuple(grounded_promotions)
        accepted_recommendations = tuple(recommendations)

        if nominated_promotion_code is None:
            if evidence:
                return _error_outcome("promotion_nomination_missing")
            return PromotionPricingOutcome(promotion=None, pricing=None)

        nominated_key = nominated_promotion_code.strip().casefold()
        promotion = next(
            (item for item in evidence if item.code.casefold() == nominated_key),
            None,
        )
        if promotion is None:
            return _error_outcome("ungrounded_promotion_code")

        if not promotion.valid:
            return PromotionPricingOutcome(promotion=promotion, pricing=None)
        if not accepted_recommendations:
            return PromotionPricingOutcome(promotion=promotion, pricing=None)

        try:
            pricing = _calculate_price(accepted_recommendations[0], promotion)
        except (DecimalException, TypeError, ValueError):
            return PromotionPricingOutcome(
                promotion=promotion,
                pricing=None,
                errors=(_safe_error("pricing_calculation_failed"),),
            )
        return PromotionPricingOutcome(promotion=promotion, pricing=pricing)


def _calculate_price(
    recommendation: HydratedRecommendation,
    promotion: DiscountValidationResult,
) -> CalculatedPrice:
    base_price = recommendation.price
    percentage = promotion.discount_percent
    if (
        not isinstance(base_price, Decimal)
        or not base_price.is_finite()
        or base_price < 0
        or recommendation.currency != "GBP"
        or not promotion.valid
        or promotion.reason != "active"
        or percentage is None
        or not percentage.is_finite()
        or not Decimal("0") <= percentage <= Decimal("100")
    ):
        raise ValueError("invalid authoritative pricing input")

    raw_discount = base_price * percentage / Decimal("100")
    discount_amount = raw_discount.quantize(
        GBP_QUANTUM,
        rounding=GBP_ROUNDING,
    )
    final_price = (base_price - discount_amount).quantize(
        GBP_QUANTUM,
        rounding=GBP_ROUNDING,
    )
    if final_price < 0:
        raise ValueError("calculated price must not be negative")

    return CalculatedPrice(
        product_id=recommendation.product_id,
        base_price=base_price,
        discount_amount=discount_amount,
        final_price=final_price,
        currency="GBP",
        discount_code=promotion.code,
        discount_percent=percentage,
    )


def _error_outcome(code: PromotionPricingErrorCode) -> PromotionPricingOutcome:
    return PromotionPricingOutcome(
        promotion=None,
        pricing=None,
        errors=(_safe_error(code),),
    )


def _safe_error(code: PromotionPricingErrorCode) -> PromotionPricingError:
    return PromotionPricingError(code=code, message=_ERROR_MESSAGES[code])
