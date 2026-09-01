"""Tests for deterministic recommendation validation and hydration."""

from decimal import Decimal
from pathlib import Path

import pytest

from salesagent.domain.models import Product
from salesagent.repositories.products import ProductRepository
from salesagent.repositories.promotions import PromotionRepository
from salesagent.services.commerce import CommerceService
from salesagent.services.recommendations import RecommendationHydrator

ROOT = Path(__file__).resolve().parents[1]


def commerce_service() -> CommerceService:
    return CommerceService(
        ProductRepository(ROOT / "data" / "products.json"),
        PromotionRepository(ROOT / "data" / "discounts.json"),
    )


class RecordingCommerceService(CommerceService):
    def __init__(self) -> None:
        super().__init__(
            ProductRepository(ROOT / "data" / "products.json"),
            PromotionRepository(ROOT / "data" / "discounts.json"),
        )
        self.requested_ids: list[str] = []

    def get_product(self, product_id: str) -> Product | None:
        self.requested_ids.append(product_id)
        return super().get_product(product_id)


class FailingCommerceService(CommerceService):
    def __init__(self) -> None:
        pass

    def get_product(self, product_id: str) -> Product | None:
        del product_id
        raise RuntimeError("repository secret")


class CanonicalProductCommerce(CommerceService):
    def __init__(self, product: Product) -> None:
        self.product = product

    def get_product(self, product_id: str) -> Product | None:
        del product_id
        return self.product


def test_empty_nominations_are_valid_and_vacuously_verified() -> None:
    result = RecommendationHydrator(commerce_service()).hydrate([], set())

    assert result.recommendations == ()
    assert result.accepted_product_ids == ()
    assert result.all_products_exist is True
    assert result.prices_match_catalogue is True
    assert result.urls_match_catalogue is True
    assert result.stock_claims_validated is True
    assert result.validation_errors == ()


def test_hydration_preserves_order_canonical_facts_decimal_and_availability() -> None:
    result = RecommendationHydrator(commerce_service()).hydrate(
        ["jkt-003", "JKT-001", "JKT-002"],
        {"JKT-001", "JKT-002", "JKT-003"},
    )

    assert result.accepted_product_ids == ("JKT-003", "JKT-001", "JKT-002")
    assert [item.availability for item in result.recommendations] == [
        "in_stock",
        "partial",
        "out_of_stock",
    ]
    first = result.recommendations[0]
    assert first.name == "Ridgeway Rain Shell"
    assert first.price == Decimal("110.00")
    assert isinstance(first.price, Decimal)
    assert first.currency == "GBP"
    assert first.product_url == "/products/ridgeway-rain-shell"
    assert not hasattr(first, "matched_variant")


def test_mixed_nominations_return_only_existing_grounded_cards() -> None:
    result = RecommendationHydrator(commerce_service()).hydrate(
        ["JKT-003", "UNKNOWN", "JKT-004"], {"JKT-003"}
    )

    assert result.accepted_product_ids == ("JKT-003",)
    assert result.all_products_exist is False
    assert result.validation_errors == (
        "unknown_product_id:UNKNOWN",
        "ungrounded_product_id:JKT-004",
    )


def test_duplicates_are_case_insensitive_and_not_refetched() -> None:
    commerce = RecordingCommerceService()
    result = RecommendationHydrator(commerce).hydrate(
        ["jkt-003", " JKT-003 "], {"jKt-003"}
    )

    assert result.accepted_product_ids == ("JKT-003",)
    assert result.validation_errors == ("duplicate_product_id:JKT-003",)
    assert commerce.requested_ids == ["jkt-003"]


def test_every_first_seen_nomination_is_refetched_through_commerce() -> None:
    commerce = RecordingCommerceService()

    RecommendationHydrator(commerce).hydrate(
        ["JKT-003", "UNKNOWN", "JKT-004"], {"JKT-003"}
    )

    assert commerce.requested_ids == ["JKT-003", "UNKNOWN", "JKT-004"]


def test_direct_calls_cannot_bypass_the_three_nomination_limit() -> None:
    with pytest.raises(ValueError, match="at most three"):
        RecommendationHydrator(commerce_service()).hydrate(
            ["JKT-001", "JKT-002", "JKT-003", "JKT-004"],
            {"JKT-001", "JKT-002", "JKT-003", "JKT-004"},
        )


def test_lookup_failure_is_safe_validation_evidence() -> None:
    result = RecommendationHydrator(FailingCommerceService()).hydrate(
        ["JKT-001"], {"JKT-001"}
    )

    assert result.recommendations == ()
    assert result.all_products_exist is False
    assert result.validation_errors == ("product_lookup_failed:JKT-001",)
    assert "secret" not in repr(result)


def test_unknown_and_duplicate_rejected_id_displays_are_single_line_and_bounded() -> (
    None
):
    unsafe_id = f"  {'X' * 70}\n\t\x00tail  "
    result = RecommendationHydrator(commerce_service()).hydrate(
        [unsafe_id, unsafe_id], set()
    )

    assert [error.split(":", 1)[0] for error in result.validation_errors] == [
        "unknown_product_id",
        "duplicate_product_id",
    ]
    for error in result.validation_errors:
        display = error.split(":", 1)[1]
        assert len(display) <= 64
        assert display.endswith("…")
        assert "\n" not in display
        assert "\t" not in display
        assert "\x00" not in display


def test_ungrounded_canonical_id_display_is_single_line_and_bounded() -> None:
    base_product = commerce_service().get_product("JKT-003")
    assert base_product is not None
    unsafe_canonical_id = f"{'Y' * 40}\n\t\x00{'Z' * 40}"
    product = base_product.model_copy(update={"id": unsafe_canonical_id})
    result = RecommendationHydrator(CanonicalProductCommerce(product)).hydrate(
        ["lookup-id"], set()
    )

    assert len(result.validation_errors) == 1
    error = result.validation_errors[0]
    assert error.startswith("ungrounded_product_id:")
    display = error.split(":", 1)[1]
    assert len(display) <= 64
    assert display.endswith("…")
    assert "\n" not in display
    assert "\t" not in display
    assert "\x00" not in display
