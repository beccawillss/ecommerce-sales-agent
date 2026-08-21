"""Behaviour tests for the deterministic commerce service."""

from collections.abc import Iterable
from decimal import Decimal
from pathlib import Path

import pytest

from salesagent.domain.models import Product, ProductSearchCriteria
from salesagent.repositories.products import ProductRepository
from salesagent.repositories.promotions import PromotionRepository
from salesagent.services.commerce import CommerceService

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def commerce() -> CommerceService:
    return CommerceService(
        products=ProductRepository(ROOT / "data" / "products.json"),
        promotions=PromotionRepository(ROOT / "data" / "discounts.json"),
    )


def product_ids(products: Iterable[Product]) -> list[str]:
    return [product.id for product in products]


def test_hiking_jacket_search_under_160_includes_apex(
    commerce: CommerceService,
) -> None:
    products = commerce.search_products(
        ProductSearchCriteria(
            category="JACKET",
            activity="Hiking",
            maximum_price=Decimal("160.00"),
        )
    )

    assert "JKT-001" in product_ids(products)
    assert all(product.price <= Decimal("160.00") for product in products)


def test_moderate_rain_hiking_search_surfaces_ridgeway(
    commerce: CommerceService,
) -> None:
    products = commerce.search_products(
        ProductSearchCriteria(
            category="jacket",
            activity="hiking",
            weather=("moderate-rain",),
            maximum_price=Decimal("120.00"),
        )
    )

    assert product_ids(products) == ["JKT-003"]


def test_in_stock_lightweight_cycling_search_surfaces_trail_breeze(
    commerce: CommerceService,
) -> None:
    products = commerce.search_products(
        ProductSearchCriteria(
            activity="cycling",
            features=("lightweight",),
            in_stock_only=True,
        )
    )

    assert product_ids(products) == ["JKT-005"]


def test_cold_dry_walking_search_surfaces_insulated_jacket(
    commerce: CommerceService,
) -> None:
    products = commerce.search_products(
        ProductSearchCriteria(
            category="jacket",
            activity="walking",
            weather=("cold", "dry"),
            features=("warm",),
        )
    )

    assert product_ids(products) == ["INS-001"]


def test_impossible_filters_return_no_products(commerce: CommerceService) -> None:
    products = commerce.search_products(
        ProductSearchCriteria(
            category="socks",
            features=("waterproof", "electronic"),
        )
    )

    assert products == ()


def test_colour_and_size_must_exist_on_the_same_variant(
    commerce: CommerceService,
) -> None:
    products = commerce.search_products(
        ProductSearchCriteria(colour="ocean blue", size="m")
    )

    assert product_ids(products) == ["JKT-003", "JKT-001"]


def test_in_stock_only_excludes_matching_zero_stock_variants(
    commerce: CommerceService,
) -> None:
    without_stock_filter = commerce.search_products(
        ProductSearchCriteria(
            activity="cycling",
            features=("lightweight",),
        )
    )
    with_stock_filter = commerce.search_products(
        ProductSearchCriteria(
            activity="cycling",
            features=("lightweight",),
            in_stock_only=True,
        )
    )

    assert product_ids(without_stock_filter) == ["JKT-002", "JKT-005"]
    assert product_ids(with_stock_filter) == ["JKT-005"]


def test_search_order_is_price_then_product_id(commerce: CommerceService) -> None:
    first_search = commerce.search_products(ProductSearchCriteria())
    second_search = commerce.search_products(ProductSearchCriteria())
    expected = sorted(first_search, key=lambda product: (product.price, product.id))

    assert list(first_search) == expected
    assert second_search == first_search


@pytest.mark.parametrize(
    ("product_id", "colour", "size", "stock", "available", "status"),
    [
        ("JKT-001", "Ocean Blue", "M", 4, True, "in_stock"),
        ("JKT-001", "Black", "M", 0, False, "out_of_stock"),
        ("JKT-001", "Ocean Blue", "XL", None, False, "variant_not_found"),
        ("NOT-A-PRODUCT", "Black", "M", None, False, "product_not_found"),
    ],
)
def test_inventory_outcomes_are_explicit(
    commerce: CommerceService,
    product_id: str,
    colour: str,
    size: str,
    stock: int | None,
    available: bool,
    status: str,
) -> None:
    result = commerce.check_inventory(product_id, colour, size)

    assert result.stock == stock
    assert result.available is available
    assert result.status == status


def test_total_stock_is_derived_from_variants(commerce: CommerceService) -> None:
    product = commerce.get_product("JKT-002")

    assert product is not None
    assert product.total_stock == 0


@pytest.mark.parametrize(
    ("code", "valid", "discount_percent", "reason"),
    [
        ("WELCOME10", True, Decimal("10"), "active"),
        ("welcome10", True, Decimal("10"), "active"),
        ("SUMMER20", False, None, "inactive"),
        ("STAFF99", False, None, "unknown_code"),
        ("SECRET75", False, None, "unknown_code"),
    ],
)
def test_discount_validation_comes_from_promotion_data(
    commerce: CommerceService,
    code: str,
    valid: bool,
    discount_percent: Decimal | None,
    reason: str,
) -> None:
    result = commerce.validate_discount(code)

    assert result.valid is valid
    assert result.discount_percent == discount_percent
    assert result.reason == reason
