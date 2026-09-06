"""Tests for deterministic promotion resolution and GBP pricing."""

from decimal import Decimal
from typing import Literal, cast

import pytest

from salesagent.domain.models import DiscountValidationResult
from salesagent.services.pricing import PromotionPricingOutcome, PromotionPricingService
from salesagent.services.recommendations import HydratedRecommendation


def promotion(
    *,
    code: str = "WELCOME10",
    valid: bool = True,
    percentage: str | None = "10",
    reason: str = "active",
) -> DiscountValidationResult:
    return DiscountValidationResult.model_validate(
        {
            "code": code,
            "valid": valid,
            "discount_percent": percentage,
            "reason": reason,
        }
    )


def recommendation(
    product_id: str,
    price: Decimal,
    *,
    currency: str = "GBP",
) -> HydratedRecommendation:
    return HydratedRecommendation(
        product_id=product_id,
        name=f"Product {product_id}",
        price=price,
        currency=cast(Literal["GBP"], currency),
        product_url=f"/products/{product_id.casefold()}",
        availability="in_stock",
    )


def resolve(
    *,
    nominated_code: str | None = "WELCOME10",
    evidence: tuple[DiscountValidationResult, ...] | None = None,
    recommendations: tuple[HydratedRecommendation, ...] | None = None,
) -> PromotionPricingOutcome:
    return PromotionPricingService().resolve(
        nominated_promotion_code=nominated_code,
        grounded_promotions=evidence if evidence is not None else (promotion(),),
        recommendations=(
            recommendations
            if recommendations is not None
            else (recommendation("JKT-001", Decimal("145.00")),)
        ),
    )


def test_active_promotion_calculates_authoritative_internal_quote() -> None:
    outcome = resolve(nominated_code=" welcome10 ")

    assert outcome.promotion == promotion()
    assert outcome.errors == ()
    assert outcome.pricing is not None
    assert outcome.pricing.product_id == "JKT-001"
    assert outcome.pricing.base_price == Decimal("145.00")
    assert outcome.pricing.discount_amount == Decimal("14.50")
    assert outcome.pricing.final_price == Decimal("130.50")
    assert outcome.pricing.currency == "GBP"
    assert outcome.pricing.discount_code == "WELCOME10"
    assert outcome.pricing.discount_percent == Decimal("10")
    assert outcome.pricing.base_price - outcome.pricing.discount_amount == (
        outcome.pricing.final_price
    )


@pytest.mark.parametrize(
    ("base_price", "percentage", "discount", "final_price"),
    [
        ("0.05", "10", "0.01", "0.04"),
        ("0.20", "12.5", "0.03", "0.17"),
        ("18.00", "0", "0.00", "18.00"),
        ("18.00", "100", "18.00", "0.00"),
    ],
)
def test_pricing_uses_discount_first_half_up_penny_rounding(
    base_price: str,
    percentage: str,
    discount: str,
    final_price: str,
) -> None:
    outcome = resolve(
        evidence=(promotion(percentage=percentage),),
        recommendations=(recommendation("TEST", Decimal(base_price)),),
    )

    assert outcome.pricing is not None
    assert outcome.pricing.base_price == Decimal(base_price)
    assert outcome.pricing.discount_amount == Decimal(discount)
    assert outcome.pricing.final_price == Decimal(final_price)
    assert outcome.pricing.base_price - outcome.pricing.discount_amount == (
        outcome.pricing.final_price
    )


@pytest.mark.parametrize(
    ("evidence", "reason"),
    [
        (
            promotion(
                code="SUMMER20",
                valid=False,
                percentage=None,
                reason="inactive",
            ),
            "inactive",
        ),
        (
            promotion(
                code="STAFF99",
                valid=False,
                percentage=None,
                reason="unknown_code",
            ),
            "unknown_code",
        ),
    ],
)
def test_negative_promotion_result_is_returned_without_pricing(
    evidence: DiscountValidationResult,
    reason: str,
) -> None:
    outcome = resolve(nominated_code=evidence.code, evidence=(evidence,))

    assert outcome.promotion is not None
    assert outcome.promotion.valid is False
    assert outcome.promotion.reason == reason
    assert outcome.pricing is None
    assert outcome.errors == ()


def test_no_nomination_without_evidence_is_an_empty_normal_outcome() -> None:
    outcome = resolve(nominated_code=None, evidence=())

    assert outcome.promotion is None
    assert outcome.pricing is None
    assert outcome.errors == ()


def test_evidence_without_nomination_is_a_safe_partial_outcome() -> None:
    outcome = resolve(nominated_code=None)

    assert outcome.promotion is None
    assert outcome.pricing is None
    assert [error.code for error in outcome.errors] == ["promotion_nomination_missing"]
    assert "WELCOME10" not in outcome.errors[0].message


def test_ungrounded_nomination_is_a_safe_partial_outcome() -> None:
    outcome = resolve(nominated_code="STAFF99")

    assert outcome.promotion is None
    assert outcome.pricing is None
    assert [error.code for error in outcome.errors] == ["ungrounded_promotion_code"]
    assert "STAFF99" not in outcome.errors[0].message


def test_valid_promotion_without_accepted_recommendation_has_no_pricing() -> None:
    outcome = resolve(recommendations=())

    assert outcome.promotion == promotion()
    assert outcome.pricing is None
    assert outcome.errors == ()


def test_pricing_targets_first_recommendation_in_final_accepted_order() -> None:
    accepted = (
        recommendation("JKT-001", Decimal("145.00")),
        recommendation("JKT-003", Decimal("110.00")),
    )

    outcome = resolve(recommendations=accepted)

    assert outcome.pricing is not None
    assert outcome.pricing.product_id == "JKT-001"
    assert outcome.pricing.base_price == Decimal("145.00")


def test_invalid_authoritative_input_omits_only_pricing_safely() -> None:
    invalid_currency = recommendation(
        "JKT-001",
        Decimal("145.00"),
        currency="USD",
    )

    outcome = resolve(recommendations=(invalid_currency,))

    assert outcome.promotion == promotion()
    assert outcome.pricing is None
    assert [error.code for error in outcome.errors] == ["pricing_calculation_failed"]
    assert "USD" not in outcome.errors[0].message
